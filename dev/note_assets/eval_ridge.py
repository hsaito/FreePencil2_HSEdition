"""サブディビジョンを適用したハイポリで、眉の出っ張りに線を出す試作。

いまの島の切り方は「辺ごとの二面角 > しきい値」。Apply すると1つの60度の
曲がりが4つの15度に分かれるので、この見方では拾えない。60度では何も切れず、
5度まで下げるとメッシュの格子が全部線になる。

そこで**長さで割る**。曲がりの量そのものではなく、単位長さあたりの曲がり
(=曲率)を見る。

    k = 二面角 / 辺の長さ * 物体サイズ        (無次元)

ケージ: 60度 / L        -> 60/L
Apply : 15度 / (L/4)    -> 60/L        …同じ値になる

面を細かくしても値が変わらないので、しきい値が段数に依存しない。これが
「サブディビありと適用後で同じ絵」に必要な性質でもある。

ただし辺を切っただけでは線は出ない。塗り分け法は**閉じた領域**の色差で
線を作るので、切り口が閉じていない稜線は島を分けられず色差がゼロになる。
だから2通り試す。

  edge  曲率がしきい値を超えた辺を境界にする(素直な案。閉じる保証なし)
  band  曲率がしきい値を超えた**面**を1つの領域にまとめる(帯。必ず閉じる)
  bandN 帯を稜線の尾根だけに細める(非極大抑制。線が二重になるのを防ぐ)

比較用にケージ(未適用)の60度も撮る。判定は画像で行う(CLAUDE.md)。

    blender -b --factory-startup --python eval_ridge.py -- [--levels 2]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "ridge"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "800"))
LEVELS = int(arg("--levels", "2"))
MERGE_PCT = float(arg("--merge", "0.05"))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# --------------------------------------------------------------- 曲率
def edge_curvature(topo, mesh):
    """辺ごとの「単位長さあたりの曲がり」を物体サイズで無次元化して返す。

    戻り値は (k, convex)。convex は凸(出っ張り)なら True。
    """
    nv = len(mesh.vertices)
    co = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    ev = np.empty(topo.n_edges * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    length = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))

    ang = np.nan_to_num(topo.angle.astype(np.float64), nan=0.0)
    k = np.zeros(topo.n_edges, dtype=np.float64)
    ok = topo.two_face & (length > 1e-12)
    k[ok] = np.degrees(ang[ok]) / length[ok] * size

    # 凸か凹か。隣の面の重心が自分の面の裏側にあれば凸
    nf = topo.n_faces
    fn = np.empty(nf * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", fn)
    fn = fn.reshape(-1, 3).astype(np.float64)
    fc = np.empty(nf * 3, dtype=np.float32)
    mesh.polygons.foreach_get("center", fc)
    fc = fc.reshape(-1, 3).astype(np.float64)
    convex = np.zeros(topo.n_edges, dtype=bool)
    a = topo.face_a[ok].astype(np.int64)
    b = topo.face_b[ok].astype(np.int64)
    convex[ok] = np.einsum("ij,ij->i", fn[a], fc[b] - fc[a]) < 0.0
    return k, convex, size


def face_edges(mesh):
    """面 -> その辺番号(ループ順)。CSR で返す。"""
    nf = len(mesh.polygons)
    nl = len(mesh.loops)
    le = np.empty(nl, dtype=np.int32)
    mesh.loops.foreach_get("edge_index", le)
    totals = np.empty(nf, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)
    first = np.zeros(nf + 1, dtype=np.int64)
    np.cumsum(totals, out=first[1:])
    return le, first, totals


def nms_ridge(mesh, k):
    """稜線を横切る向きに非極大抑制する。

    四角面なら「向かい合う辺」がちょうど稜線を横切る方向の隣になる。
    自分の曲率がその両方以上のときだけ尾根と見なす。
    """
    le, first, totals = face_edges(mesh)
    nf = len(totals)
    keep = np.ones(len(k), dtype=bool)
    for f in range(nf):
        n = int(totals[f])
        if n < 4:
            continue
        s = int(first[f])
        ring = le[s:s + n]
        opp = ring[(np.arange(n) + n // 2) % n]
        worse = k[ring] < k[opp]
        keep[ring[worse]] = False
    return keep


# --------------------------------------------------------------- 塗り
def paint(obj, topo, seed_int=42):
    from freepencil2 import utils, mesh_islands
    me = obj.data
    nf = len(me.polygons)
    islands = topo.islands
    nbrs = topo.island_adjacency(boundary_only=True)
    mesh_islands.add_loose_part_proximity(topo, me, nbrs)
    classes = utils.color_graph_greedy(nbrs)
    n_cls = (max(classes) + 1) if classes else 1
    pal, _d, _l = utils.palette_for_diversity(
        0.5, min(len(islands), 16), seed_int, min_k=n_cls)
    classes, _n = utils.diversify_island_colors(nbrs, classes, pal, 0.5)

    cols = np.zeros((nf, 3), dtype=np.float32)
    for i, faces in enumerate(islands):
        cols[faces] = pal[classes[i]]
    attr = me.color_attributes.get("mecha_color")
    if attr is None:
        attr = me.color_attributes.new(name="mecha_color", type='BYTE_COLOR',
                                       domain='CORNER')
    totals = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_total", totals)
    idx = np.repeat(np.arange(nf), totals)
    buf = np.zeros(len(me.loops) * 4, dtype=np.float32)
    buf[0::4] = cols[idx, 0]
    buf[1::4] = cols[idx, 1]
    buf[2::4] = cols[idx, 2]
    buf[3::4] = 1.0
    attr.data.foreach_set("color", buf)
    me.color_attributes.active_color = attr
    return len(islands), n_cls


def look(o, close):
    """正面やや斜めから。close=True なら目のあたりに寄る。"""
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    pts = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    ctr = (mn + mx) * 0.5
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 1e-4)
    tgt = ctr + Vector((0.0, 0.0, size * 0.12)) if close else ctr
    cd = bpy.data.cameras.new("C")
    cd.lens = 50.0
    cd.clip_end = size * 40
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    d = Vector((0.35, -1.0, 0.30)).normalized()
    cam.location = tgt + d * (size * (0.9 if close else 1.9))
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.lights.new("L", type="AREA")
    lt.energy = size * size * 900.0
    lt.size = size * 2.0
    lo = bpy.data.objects.new("L", lt)
    sc.collection.objects.link(lo)
    lo.location = tgt + Vector((0.4, -0.8, 1.4)) * size


def render_vc(sc, o, png):
    mat = bpy.data.materials.new("VC")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "mecha_color"
    em = nt.nodes.new("ShaderNodeEmission")
    ou = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
    keep = [s.material for s in o.material_slots]
    for s in o.material_slots:
        s.material = mat
    kc, kv = sc.use_nodes, sc.view_settings.view_transform
    sc.use_nodes = False
    sc.view_settings.view_transform = 'Standard'
    fp_batch.render_still(sc, png, 1)
    sc.use_nodes, sc.view_settings.view_transform = kc, kv
    for s, m2 in zip(o.material_slots, keep):
        s.material = m2


# --------------------------------------------------------------- 本体
def one(key, mode, thr, applied, close=True):
    from freepencil2 import mesh_islands, fp_core
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("Sub", type="SUBSURF")
    m.levels = m.render_levels = LEVELS
    if applied:
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
    me = o.data
    topo = mesh_islands.MeshTopology(me)

    if mode == "deg60":
        topo.mark_boundaries(np.radians(60.0), False, False)
    else:
        k, convex, size = edge_curvature(topo, me)
        if mode == "edge":
            b = (k >= thr) & topo.two_face
        else:
            hot = k >= thr
            if mode == "bandN":
                hot &= nms_ridge(me, k)
            # 面ごとに「稜線に載っているか」を決め、領域が変わる辺を境界に
            le, first, totals = face_edges(me)
            nf = topo.n_faces
            face_hot = np.zeros(nf, dtype=bool)
            for f in range(nf):
                s = int(first[f])
                face_hot[f] = hot[le[s:s + int(totals[f])]].any()
            b = np.zeros(topo.n_edges, dtype=bool)
            ok = topo.two_face
            b[ok] = face_hot[topo.face_a[ok].astype(np.int64)] \
                != face_hot[topo.face_b[ok].astype(np.int64)]
        topo.is_boundary = b
    topo.build_islands()
    if MERGE_PCT > 0.0 and len(topo.islands) > 1:
        mesh_islands.merge_small_islands(topo, MERGE_PCT)
    n_isl, n_cls = paint(o, topo)

    if not o.material_slots:
        me.materials.append(bpy.data.materials.new("FP_Mat"))
    for s in o.material_slots:
        if s.material is None:
            s.material = bpy.data.materials.new("FP_Mat")
        s.material.use_nodes = True
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_preview_mode = 'NONE'
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    fp_core.setup_aov(sc, bpy.context.view_layer)
    fp_core.setup_compositor(sc, bpy.context.view_layer)

    look(o, close)
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    fp_batch.render_still(sc, OUT / f"{key}_line.png", 1)
    render_vc(sc, o, OUT / f"{key}_vc.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    say(f"{key}: 面{topo.n_faces:,} 島{n_isl} 色{n_cls}")
    return {"key": key, "mode": mode, "thr": thr, "applied": applied,
            "faces": topo.n_faces, "islands": n_isl, "classes": n_cls}


CASES = [
    ("cage60", "deg60", 0.0, False),
    ("app60", "deg60", 0.0, True),
]
for t in (40.0, 70.0, 110.0, 160.0):
    CASES.append((f"app_edge{t:.0f}", "edge", t, True))
    CASES.append((f"app_band{t:.0f}", "band", t, True))
    CASES.append((f"app_bandN{t:.0f}", "bandN", t, True))
    CASES.append((f"cage_band{t:.0f}", "band", t, False))


def main():
    fp_batch.install_addon()
    rows = []
    for key, mode, thr, applied in CASES:
        try:
            rows.append(one(key, mode, thr, applied))
        except Exception as e:                           # noqa: BLE001
            import traceback
            traceback.print_exc()
            say(f"{key}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"levels": LEVELS, "rows": rows}, ensure_ascii=False,
                   indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
