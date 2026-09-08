"""つながっていないパーツで色を分け、そこへ緩めの法線を足す。

鋭角で島に切るのをやめる。**辺で繋がった塊(ルースパーツ)ごとに1色**だけ
置く。1つのパーツの中はどれだけ広くても同じ色になる。

パーツ同士はメッシュの辺を共有しないので、そのままだと隣接判定に入らず
同じ色になってしまう。そこは今日入れた近接隣接
(mesh_islands.add_loose_part_proximity)で「近ければ隣」と見なす。

そのうえで法線の残差を薄く足す。

    col = パーツの色 + amp * (法線 - 距離 R ぶん均した法線)

パーツの色は面ごとに一定なので、足した残差はパーツの中だけをゆるく
揺らす。パーツ境界の段差はそのまま残る。

硬い形(メカ)で稜線が残るかが焦点。ベベルで角が丸められていると残差が
小さくなるので、R を振って確かめる。

    blender -b --factory-startup --python eval_part_normal.py -- \
        [--amps 0.15,0.25,0.35] [--rs 0.02,0.04]
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


OUT = Path(arg("--out", str(HERE / "out" / "part_normal"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
LEVELS = int(arg("--levels", "2"))
ZOOM = float(arg("--zoom", "1.7"))
AMPS = [float(x) for x in arg("--amps", "0.15,0.25,0.35").split(",")]
RS = [float(x) for x in arg("--rs", "0.02,0.04").split(",")]
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# ------------------------------------------------------------------ 形
def suzanne(applied):
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("Sub", type="SUBSURF")
    m.levels = m.render_levels = LEVELS
    if applied:
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o


def mecha_hipoly():
    """箱と円柱を寄せ集めて焼いた硬い形。ハイポリのメカに近い条件。"""
    parts = []
    specs = [("cube", (0, 0, 0), (1.2, 0.8, 0.5)),
             ("cube", (1.6, 0, 0.2), (0.5, 0.5, 0.9)),
             ("cube", (-1.5, 0.1, 0.3), (0.6, 0.7, 0.4)),
             ("cyl", (0.2, 0.0, 1.0), (0.35, 0.35, 0.7)),
             ("cyl", (-0.9, -0.6, -0.6), (0.25, 0.25, 0.9))]
    for kind, loc, sc in specs:
        if kind == "cube":
            bpy.ops.mesh.primitive_cube_add(location=loc)
        else:
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, location=loc)
        o = bpy.context.object
        o.scale = sc
        parts.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.join()
    o = bpy.context.object
    b = o.modifiers.new("B", type="BEVEL")
    b.width = 0.06
    b.segments = 3
    s = o.modifiers.new("S", type="SUBSURF")
    s.levels = s.render_levels = 1
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=b.name)
    bpy.ops.object.modifier_apply(modifier=s.name)
    return o


SHAPES = [("スザンヌ(適用済み)", lambda: suzanne(True)),
          ("スザンヌ(ケージ)", lambda: suzanne(False)),
          ("メカ(ハイポリ)", mecha_hipoly)]


# -------------------------------------------------------------- パーツ色
def part_of_face(mesh, topo):
    """面 -> ルースパーツ番号。"""
    from freepencil2 import mesh_islands
    nv = len(mesh.vertices)
    ev = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    lab = mesh_islands.connected_components(ev[:, 0], ev[:, 1], nv)
    lv = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    starts = np.empty(topo.n_faces, dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    raw = lab[lv[starts]]
    _u, idx = np.unique(raw, return_inverse=True)
    return idx.astype(np.int64)


def paint_by_part(obj, seed_int=42, min_dist=0.5):
    from freepencil2 import mesh_islands, utils
    mesh = obj.data
    topo = mesh_islands.MeshTopology(mesh)
    pf = part_of_face(mesh, topo)
    n_part = int(pf.max()) + 1
    islands = [np.flatnonzero(pf == i).astype(np.int32)
               for i in range(n_part)]
    topo.set_islands(islands)

    # パーツ同士は辺を共有しないので、隣接は近接判定で作る
    nbrs = [set() for _ in range(n_part)]
    n_prox = mesh_islands.add_loose_part_proximity(topo, mesh, nbrs)
    classes = utils.color_graph_greedy(nbrs)
    n_cls = (max(classes) + 1) if classes else 1
    pal, _d, _l = utils.palette_for_diversity(
        min_dist, min(n_part, 16), seed_int, min_k=n_cls)
    classes, n_used = utils.diversify_island_colors(nbrs, classes, pal,
                                                   min_dist)
    cols = np.zeros((topo.n_faces, 3), dtype=np.float64)
    for i, faces in enumerate(islands):
        cols[faces] = pal[classes[i]]
    return topo, cols, n_part, n_prox, n_used


# ---------------------------------------------------------------- 残差
def residual(mesh, r_frac):
    nv = len(mesh.vertices)
    co = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    vn = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("normal", vn)
    vn = vn.reshape(-1, 3).astype(np.float64)
    ev = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)

    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    el = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    mean_edge = float(np.mean(el)) if len(el) else size
    # 均す回数は距離から。回数固定だと粗いメッシュだけ潰れる(実測済み)
    iters = int(round((size * r_frac / max(mean_edge, 1e-9)) ** 2))

    a, b = ev[:, 0].astype(np.int64), ev[:, 1].astype(np.int64)
    deg = np.bincount(np.concatenate([a, b]), minlength=nv).astype(np.float64)
    deg[deg == 0] = 1.0
    m = vn.copy()
    for _ in range(iters):
        acc = m.copy()
        np.add.at(acc, a, m[b])
        np.add.at(acc, b, m[a])
        m = acc / (deg + 1.0)[:, None]
    ln = np.linalg.norm(m, axis=1)
    ln[ln < 1e-12] = 1.0
    m /= ln[:, None]
    d = np.clip((vn - m) * 0.5, -1.0, 1.0)      # 180度ズレで ±1
    lv = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    return d[lv], iters


def write_colors(mesh, face_cols, res, amp):
    nf = len(mesh.polygons)
    totals = np.empty(nf, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)
    idx = np.repeat(np.arange(nf), totals)
    col = np.clip(face_cols[idx] + amp * res, 0.0, 1.0)
    attr = mesh.color_attributes.get("mecha_color")
    if attr is None:
        attr = mesh.color_attributes.new(name="mecha_color", type='BYTE_COLOR',
                                         domain='CORNER')
    buf = np.ones(len(mesh.loops) * 4, dtype=np.float32)
    buf[0::4] = col[:, 0]
    buf[1::4] = col[:, 1]
    buf[2::4] = col[:, 2]
    attr.data.foreach_set("color", buf)
    mesh.color_attributes.active_color = attr
    return float(np.abs(amp * res).max())


# ------------------------------------------------------------------ 撮影
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
    d = Vector((0.30, -1.0, 0.14)).normalized()
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


def one(tag, make, key, amp, r_frac):
    from freepencil2 import fp_core
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    o = make()
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.shade_smooth()

    _topo, cols, n_part, n_prox, n_used = paint_by_part(o)
    res, iters = residual(o.data, r_frac)
    mx = write_colors(o.data, cols, res, amp)

    if not o.material_slots:
        o.data.materials.append(bpy.data.materials.new("FP_Mat"))
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

    look(o, ZOOM)
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    full = f"{tag}_{key}"
    fp_batch.render_still(sc, OUT / f"{full}_line.png", 1)
    render_vc(sc, o, OUT / f"{full}_vc.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{full}.blend"))
    say(f"{full}: 面{len(o.data.polygons):,} パーツ{n_part} 近接{n_prox} "
        f"色{n_used} 残差最大{mx:.3f}(均し{iters}回)")
    return {"key": full, "amp": amp, "r": r_frac, "parts": n_part}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"q{i:02d}"
        for r in RS:
            for amp in AMPS:
                key = f"r{r * 100:.0f}a{amp * 100:.0f}"
                try:
                    rr = one(tag, make, key, amp, r)
                    rr["label"] = label
                    rows.append(rr)
                except Exception as e:                   # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    say(f"{tag}_{key}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
