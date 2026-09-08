"""島の育て方を「隣の面との角度」から「領域の平均法線との角度」へ変えて試す。

いまは辺ごとに angle(faceA, faceB) > しきい値 で切っている。この見方だと
Apply で1つの60度の曲がりが4つの15度に分かれた瞬間に拾えなくなる。
1辺の値しか見ないので**累積が失われる**のが原因。

そこで領域を育てるときに、隣の面ではなく**その領域の平均法線**と比べる。
なめらかな曲面を進むとズレが積み上がり、同じ物理的な曲がりの所で必ず
しきい値を超える。面を細かくしても、同じ距離で同じだけ積み上がるので
結果が変わらない ——という仮説を確かめる。

ケージと Apply 済みを同じしきい値で塗って、絵が一致するかを見る。

    blender -b --factory-startup --python eval_region_grow.py -- [--tol 25]
"""
from __future__ import annotations

import json
import math
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


OUT = Path(arg("--out", str(HERE / "out" / "region_grow"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "700"))
LEVELS = int(arg("--levels", "2"))
TOLS = [float(x) for x in arg("--tols", "15,25,35,45").split(",")]
T0 = time.time()

SHAPES = [
    ("スザンヌ", lambda: (bpy.ops.mesh.primitive_monkey_add(),
                      bpy.context.object)[1]),
    ("トーラス", lambda: (bpy.ops.mesh.primitive_torus_add(),
                      bpy.context.object)[1]),
]


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def grow_by_normal(topo, normals, tol_rad):
    """領域の平均法線からのズレで島を育てる。

    種の面から幅優先で広げ、隣の面を入れるかどうかを「いまの領域の
    平均法線との角度」で決める。隣同士の角度では累積しないが、
    平均との角度なら曲面を進むほどズレが積み上がる。
    """
    nf = topo.n_faces
    visited = np.zeros(nf, dtype=bool)
    label = np.full(nf, -1, dtype=np.int32)
    # 面 -> 隣の面(境界でない辺を通る)
    ok = topo.two_face
    a = topo.face_a[ok].astype(np.int64)
    b = topo.face_b[ok].astype(np.int64)
    order = np.argsort(np.concatenate([a, b]), kind="stable")
    src = np.concatenate([a, b])[order]
    dst = np.concatenate([b, a])[order]
    first = np.searchsorted(src, np.arange(nf + 1))

    cos_tol = math.cos(tol_rad)
    islands = []
    for seed in range(nf):
        if visited[seed]:
            continue
        visited[seed] = True
        acc = normals[seed].astype(np.float64).copy()
        mean = acc / max(np.linalg.norm(acc), 1e-12)
        members = [seed]
        queue = [seed]
        while queue:
            f = queue.pop()
            for k in range(first[f], first[f + 1]):
                g = int(dst[k])
                if visited[g]:
                    continue
                n = normals[g].astype(np.float64)
                ln = np.linalg.norm(n)
                if ln < 1e-12:
                    continue
                if float(np.dot(mean, n / ln)) < cos_tol:
                    continue
                visited[g] = True
                members.append(g)
                queue.append(g)
                acc += n
                mean = acc / max(np.linalg.norm(acc), 1e-12)
        label[np.array(members, dtype=np.int64)] = len(islands)
        islands.append(np.array(sorted(members), dtype=np.int64))
    return islands, label


def paint(obj, islands, label, seed_int=42):
    """島ごとに色を置く。既存のパレット生成をそのまま使う。"""
    from freepencil2 import utils
    me = obj.data
    nf = len(me.polygons)
    # 隣接グラフ(島境界の辺を共有する島同士)
    nbrs = [set() for _ in islands]
    from freepencil2 import mesh_islands
    topo = mesh_islands.MeshTopology(me)
    ok = topo.two_face
    la = label[topo.face_a[ok].astype(np.int64)]
    lb = label[topo.face_b[ok].astype(np.int64)]
    diff = la != lb
    for x, y in zip(la[diff].tolist(), lb[diff].tolist()):
        nbrs[x].add(y)
        nbrs[y].add(x)
    classes = utils.color_graph_greedy(nbrs)
    n_cls = (max(classes) + 1) if classes else 1
    pal, _d, _l = utils.build_palette(n_cls, seed_int)

    cols = np.zeros((nf, 3), dtype=np.float32)
    for i, faces in enumerate(islands):
        cols[faces] = pal[classes[i]]

    attr = me.color_attributes.get("mecha_color")
    if attr is None:
        attr = me.color_attributes.new(name="mecha_color", type='BYTE_COLOR',
                                       domain='CORNER')
    buf = np.zeros(len(me.loops) * 4, dtype=np.float32)
    starts = np.zeros(nf, dtype=np.int64)
    totals = np.zeros(nf, dtype=np.int64)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    for i in range(nf):
        s, t = int(starts[i]), int(totals[i])
        buf[s * 4:(s + t) * 4] = np.tile(
            np.append(cols[i], 1.0).astype(np.float32), t)
    attr.data.foreach_set("color", buf)
    me.color_attributes.active_color = attr
    return n_cls


def fit(o):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    pts = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    ctr = (mn + mx) * 0.5
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 1e-4)
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 50.0
    cd.clip_end = size * 40
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    d = Vector((0.75, -1.0, 0.45)).normalized()
    cam.location = ctr + d * (size * 2.1)
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.lights.new("L", type="AREA")
    lt.energy = size * size * 900.0
    lt.size = size * 2.0
    lo = bpy.data.objects.new("L", lt)
    bpy.context.scene.collection.objects.link(lo)
    lo.location = ctr + Vector((0.4, -0.8, 1.4)) * size


def one(tag, make, applied, tol, key):
    from freepencil2 import mesh_islands, fp_core
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    o = make()
    m = o.modifiers.new("Sub", type="SUBSURF")
    m.levels = m.render_levels = LEVELS
    if applied:
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)

    me = o.data
    nf = len(me.polygons)
    normals = np.zeros(nf * 3, dtype=np.float32)
    me.polygons.foreach_get("normal", normals)
    normals = normals.reshape(nf, 3)

    topo = mesh_islands.MeshTopology(me)
    islands, label = grow_by_normal(topo, normals, math.radians(tol))
    n_cls = paint(o, islands, label)

    if not o.material_slots:
        o.data.materials.append(bpy.data.materials.new("FP_Mat"))
    for s in o.material_slots:
        if s.material is None:
            s.material = bpy.data.materials.new("FP_Mat")
        s.material.use_nodes = True

    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False
    # STEP1 は通さない(自前で塗ったので上書きさせない)
    fp_core.setup_aov(scene, bpy.context.view_layer)
    fp_core.setup_compositor(scene, bpy.context.view_layer)

    fit(o)
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{tag}_{key}.png"
    fp_batch.render_still(scene, png, 1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{tag}_{key}.blend"))
    return {"file": png.name, "islands": len(islands), "faces": nf,
            "classes": n_cls, "tol": tol}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"r{i:02d}"
        shots = {}
        for tol in TOLS:
            for applied in (False, True):
                k = f"{'app' if applied else 'cage'}{tol:.0f}"
                try:
                    shots[k] = one(tag, make, applied, tol, k)
                except Exception as e:                   # noqa: BLE001
                    say(f"{label} {k}: 失敗 {e}")
        rows.append({"label": label, "tag": tag, "shots": shots})
        say(f"{label}: " + " / ".join(
            f"{k}島{v['islands']}" for k, v in shots.items()))
    (OUT / "index.json").write_text(
        json.dumps({"levels": LEVELS, "tols": TOLS, "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
