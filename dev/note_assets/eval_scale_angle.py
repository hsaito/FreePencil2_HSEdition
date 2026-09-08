"""「一定の距離にわたる曲がり」で島を切る試作。

いまは辺ごとの二面角で切っている。Apply で1つの60度の曲がりが4つの15度に
分かれると、1辺の値しか見ないので拾えなくなる。

そこで面法線を**一定の半径ぶん平均**してから角度を測る。半径を物体の
大きさに対する割合で決めれば、面が細かくても粗くても「同じ距離ぶん」を
見ることになり、同じ物理的な曲がりに対して同じ角度が出るはず。

  1. 平均する回数 k を「半径 ÷ 平均辺長」から決める
  2. 面法線を k 回ならす(隣の面と平均)
  3. ならした法線で辺ごとの角度を測り、しきい値で切る

種から育てる方式と違って対称で決定的なので、境界が階段状にならない。

ケージと Apply 済みを同じ設定で塗って、絵が一致するかを見る。

    blender -b --factory-startup --python eval_scale_angle.py -- \
        [--radius 0.04] [--tols 20,30,40]
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


OUT = Path(arg("--out", str(HERE / "out" / "scale_angle"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "700"))
LEVELS = int(arg("--levels", "2"))
RADIUS = float(arg("--radius", "0.04"))    # 物体の対角線に対する割合
TOLS = [float(x) for x in arg("--tols", "20,30,40").split(",")]
T0 = time.time()

SHAPES = [
    ("スザンヌ", lambda: (bpy.ops.mesh.primitive_monkey_add(),
                      bpy.context.object)[1]),
    ("トーラス", lambda: (bpy.ops.mesh.primitive_torus_add(),
                      bpy.context.object)[1]),
]


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


def smooth_normals(normals, dst, first, k):
    """隣の面と k 回平均して、法線を「広い範囲の向き」にする。"""
    n = normals.astype(np.float64).copy()
    nf = len(n)
    deg = np.diff(first).astype(np.float64)
    for _ in range(int(k)):
        acc = n.copy()
        np.add.at(acc, np.repeat(np.arange(nf), np.diff(first)), n[dst])
        n = acc / (deg + 1.0)[:, None]
        ln = np.linalg.norm(n, axis=1)
        ln[ln < 1e-12] = 1.0
        n /= ln[:, None]
    return n


def rounds_for_radius(me, topo, radius_frac):
    """半径(物体サイズ比)を、平均する回数に換算する。"""
    co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    # 平均の辺長
    ev = np.zeros(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    el = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    mean_edge = float(np.mean(el)) if len(el) else size
    k = max(0, int(round(size * radius_frac / max(mean_edge, 1e-9))))
    return k, size, mean_edge


def paint(o, label, n_islands, seed_int=42):
    from freepencil2 import utils, mesh_islands
    me = o.data
    nf = len(me.polygons)
    topo = mesh_islands.MeshTopology(me)
    ok = topo.two_face
    la = label[topo.face_a[ok].astype(np.int64)]
    lb = label[topo.face_b[ok].astype(np.int64)]
    diff = la != lb
    nbrs = [set() for _ in range(n_islands)]
    for x, y in zip(la[diff].tolist(), lb[diff].tolist()):
        nbrs[x].add(y)
        nbrs[y].add(x)
    classes = utils.color_graph_greedy(nbrs)
    n_cls = (max(classes) + 1) if classes else 1
    pal, _d, _l = utils.build_palette(n_cls, seed_int)
    cols = np.array([pal[classes[label[i]]] for i in range(nf)],
                    dtype=np.float32)

    attr = me.color_attributes.get("mecha_color")
    if attr is None:
        attr = me.color_attributes.new(name="mecha_color", type='BYTE_COLOR',
                                       domain='CORNER')
    starts = np.zeros(nf, dtype=np.int64)
    totals = np.zeros(nf, dtype=np.int64)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    buf = np.zeros(len(me.loops) * 4, dtype=np.float32)
    idx = np.repeat(np.arange(nf), totals)
    buf[0::4] = cols[idx, 0]
    buf[1::4] = cols[idx, 1]
    buf[2::4] = cols[idx, 2]
    buf[3::4] = 1.0
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
    dst, first = face_graph(topo)
    k, size, mean_edge = rounds_for_radius(me, topo, RADIUS)
    sn = smooth_normals(normals, dst, first, k)

    # ならした法線で辺ごとの角度を出し、しきい値で切る
    ok = topo.two_face
    fa = topo.face_a[ok].astype(np.int64)
    fb = topo.face_b[ok].astype(np.int64)
    dot = np.clip(np.einsum("ij,ij->i", sn[fa], sn[fb]), -1.0, 1.0)
    ang = np.degrees(np.arccos(dot))
    b = np.ones(topo.n_edges, dtype=bool)
    idx = np.flatnonzero(ok)
    b[idx] = ang > tol
    topo.is_boundary = b
    topo.build_islands()
    islands = topo.islands
    label = np.zeros(nf, dtype=np.int64)
    for i, faces in enumerate(islands):
        label[faces] = i
    n_cls = paint(o, label, len(islands))

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
            "rounds": k, "mean_edge": round(mean_edge, 4), "tol": tol}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"g{i:02d}"
        shots = {}
        for tol in TOLS:
            for applied in (False, True):
                key = f"{'app' if applied else 'cage'}{tol:.0f}"
                try:
                    shots[key] = one(tag, make, applied, tol, key)
                except Exception as e:                   # noqa: BLE001
                    say(f"{label} {key}: 失敗 {e}")
        rows.append({"label": label, "tag": tag, "shots": shots})
        say(f"{label}: " + " / ".join(
            f"{k}(平均{v['rounds']}回,島{v['islands']})"
            for k, v in shots.items()))
    (OUT / "index.json").write_text(
        json.dumps({"levels": LEVELS, "radius": RADIUS, "tols": TOLS,
                    "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
