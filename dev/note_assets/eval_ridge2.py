"""「半径 r の中で面の向きがどれだけ振れるか」で稜線を拾う試作。

辺ごとの二面角は、Apply すると1つの60度が4つの15度に割れて消える。
辺の長さで割る(曲率)案は試したが、細かいメッシュだと分母が小さくて
ノイズが暴れ、頭頂の格子まで線になった(eval_ridge.py の app_edge70)。

積分にすれば消えない。面 f の周り**半径 r 以内**の面法線を集め、
その広がり(法線コーンの開き角)を測る。

    turn(f) = 2 * max angle( n_p , mean(n) )      p は半径 r 以内の面

  ケージ  : r の中に 60度の折れが1本入る -> turn 60度
  Apply後 : r の中に 15度が4本入る       -> turn 60度   …同じ値
  なめらかな球面 : turn ≒ 2r/R           …半径で決まる小さい値

r を物体サイズの割合で決めれば、面の細かさに依存しない。しきい値を
超えた面を「稜線に載っている面」としてひとまとめの領域にする。領域なら
必ず閉じるので、塗り分け法でも確実に色差＝線になる。

ケージと Apply 済みを同じ設定で撮って、絵が一致するかも見る。

    blender -b --factory-startup --python eval_ridge2.py -- \
        [--radius 0.035] [--tols 30,45,60]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "ridge2"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "800"))
LEVELS = int(arg("--levels", "2"))
RADII = [float(x) for x in arg("--radii", "0.025,0.05").split(",")]
TOLS = [float(x) for x in arg("--tols", "30,45,60").split(",")]
SMOOTHS = [int(x) for x in arg("--smooths", "0").split(",")]
SDIST = float(arg("--sdist", "0.04"))    # 均す距離(物体サイズ比)。-1 で自動
MERGE_PCT = float(arg("--merge", "0.02"))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def face_graph(topo):
    """面 -> 隣の面 の CSR。面が2枚ある辺だけを通る。"""
    ok = topo.two_face
    a = topo.face_a[ok].astype(np.int64)
    b = topo.face_b[ok].astype(np.int64)
    src = np.concatenate([a, b])
    dst = np.concatenate([b, a])
    order = np.argsort(src, kind="stable")
    src, dst = src[order], dst[order]
    first = np.searchsorted(src, np.arange(topo.n_faces + 1))
    return dst, first


def turning(mesh, topo, radius_frac):
    """面ごとの「半径 r の中での向きの振れ幅」を度で返す。

    近傍は**面をたどった距離**で取る。ユークリッド距離の球で取ると、
    鼻の反対側や耳の裏がそのまま入ってきて振れ幅が 359 度になる
    (実測: eval_ridge2 の最初の版)。表面の上を歩いた距離でなければ
    「この場所の曲がり」にならない。
    """
    nf = len(mesh.polygons)
    fn = np.empty(nf * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", fn)
    fn = fn.reshape(-1, 3).astype(np.float64)
    ln = np.linalg.norm(fn, axis=1)
    ln[ln < 1e-12] = 1.0
    fn /= ln[:, None]
    fc = np.empty(nf * 3, dtype=np.float32)
    mesh.polygons.foreach_get("center", fc)
    fc = fc.reshape(-1, 3).astype(np.float64)

    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    r = size * radius_frac

    dst, first = face_graph(topo)
    step = np.zeros(len(dst), dtype=np.float64)
    src_of = np.repeat(np.arange(nf), np.diff(first))
    step = np.linalg.norm(fc[src_of] - fc[dst], axis=1)

    out = np.zeros(nf, dtype=np.float64)
    for i in range(nf):
        seen = {i: 0.0}
        stack = [i]
        while stack:
            f = stack.pop()
            d0 = seen[f]
            for k in range(int(first[f]), int(first[f + 1])):
                g = int(dst[k])
                d = d0 + step[k]
                if d <= r and seen.get(g, 1e30) > d:
                    seen[g] = d
                    stack.append(g)
        idx = list(seen)
        if len(idx) < 2:
            continue
        ns = fn[idx]
        m = ns.sum(axis=0)
        n_m = np.linalg.norm(m)
        if n_m < 1e-12:
            out[i] = 180.0
            continue
        m /= n_m
        d = float(np.clip(ns @ m, -1.0, 1.0).min())
        out[i] = 2.0 * np.degrees(np.arccos(d))
    return out, r, size


def smooth_rounds(mesh, dist_frac):
    """均す回数を「物体サイズに対する距離」から決める。

    回数を固定にすると、粗いケージでは頭全体が均されて稜線が消え、
    細かいメッシュでは局所しか均されない(実測: 8回固定でケージだけ眉が
    消えた)。拡散が届く距離は およそ sqrt(回数) x 辺長 なので、
    回数 = (目標距離 / 辺長)^2 にすれば面の細かさによらず同じ距離になる。
    """
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    ev = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    mean_edge = float(np.mean(np.linalg.norm(
        co[ev[:, 0]] - co[ev[:, 1]], axis=1))) or 1.0
    return int(round((size * dist_frac / mean_edge) ** 2)), mean_edge


def smooth_field(topo, val, iters):
    """面の値を隣どうしで平均する。等高線のギザギザを取るため。

    法線を平均する案は失敗した(曲がりの積み上げが消えて輪郭だけになった、
    eval_scale_angle.py)。ここで均すのは法線ではなく**スカラー場**なので、
    積み上げた値そのものは壊れない。境界線の通り道だけがなめらかになる。
    """
    if iters <= 0:
        return val
    dst, first = face_graph(topo)
    nf = topo.n_faces
    deg = np.diff(first).astype(np.float64)
    src_of = np.repeat(np.arange(nf), np.diff(first))
    v = val.astype(np.float64).copy()
    for _ in range(int(iters)):
        acc = v.copy()
        np.add.at(acc, src_of, v[dst])
        v = acc / (deg + 1.0)
    return v


def region_from_hot(topo, hot):
    """面の 2値ラベルが変わる辺を境界にする。領域は必ず閉じる。"""
    b = np.zeros(topo.n_edges, dtype=bool)
    ok = topo.two_face
    b[ok] = hot[topo.face_a[ok].astype(np.int64)] \
        != hot[topo.face_b[ok].astype(np.int64)]
    topo.is_boundary = b


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


def look(o, zoom):
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    pts = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    ctr = (mn + mx) * 0.5
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 1e-4)
    cd = bpy.data.cameras.new("C")
    cd.lens = 50.0
    cd.clip_end = size * 40
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    d = Vector((0.30, -1.0, 0.12)).normalized()
    cam.location = ctr + d * (size * zoom)
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.lights.new("L", type="AREA")
    lt.energy = size * size * 900.0
    lt.size = size * 2.0
    lo = bpy.data.objects.new("L", lt)
    sc.collection.objects.link(lo)
    lo.location = ctr + Vector((0.4, -0.8, 1.4)) * size


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


def one(key, applied, radius, tol, zoom=1.6, smooth=0, ss=1):
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

    if tol is None:                      # 比較用: いまの 60度
        topo.mark_boundaries(np.radians(60.0), False, False)
        stat = "60度"
    else:
        t, r, size = turning(me, topo, radius)
        if smooth < 0:                   # 自動: サイズ比の距離から回数を出す
            smooth, mean_edge = smooth_rounds(me, SDIST)
        t = smooth_field(topo, t, smooth)
        hot = t >= tol
        region_from_hot(topo, hot)
        stat = (f"r={radius} tol={tol:.0f} 均し{smooth}回 "
                f"稜線面{int(hot.sum())}/{topo.n_faces} "
                f"振れ中央{np.median(t):.0f}度 最大{t.max():.0f}度")
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

    look(o, zoom)
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    fp_batch.render_still(sc, OUT / f"{key}_line.png", ss)
    render_vc(sc, o, OUT / f"{key}_vc.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    say(f"{key}: 面{topo.n_faces:,} 島{n_isl} 色{n_cls}  {stat}")
    return {"key": key, "applied": applied, "radius": radius, "tol": tol,
            "faces": topo.n_faces, "islands": n_isl}


def main():
    fp_batch.install_addon()
    rows = [one("cage60", False, 0.0, None),
            one("app60", True, 0.0, None)]
    for rad in RADII:
        for tol in TOLS:
            for sm in SMOOTHS:
                tag = f"r{rad * 1000:.0f}t{tol:.0f}s{sm}"
                for applied in (True, False):
                    key = f"{'app' if applied else 'cage'}_{tag}"
                    try:
                        rows.append(one(key, applied, rad, tol, smooth=sm))
                    except Exception as e:               # noqa: BLE001
                        import traceback
                        traceback.print_exc()
                        say(f"{key}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"levels": LEVELS, "rows": rows}, ensure_ascii=False,
                   indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
