"""領域分割の境界を整えて、サブディビあり / Apply済み を一致させる。

案3(領域の平均法線で育てる)は島の数がケージと Apply 後でよく揃ったが、
境界が階段状にガタついた。原因は先着順で広げていること。面が「よく合うか」
ではなく「先に到達したか」で決まるため、境界が面の並びに沿ってしまう。

そこで割り当てを **合致度の高い順** に変える。

  1. 各領域の代表法線(面積で重みづけした平均)を持つ
  2. 優先度つき待ち行列で、代表法線とのズレが小さい面から順に取り込む
  3. 全部割り当てたら代表法線を計算し直し、種を「いちばんよく合う面」に
     置き直して 1 へ戻る

これを数回まわすと境界が落ち着く。ズレの大きい所へ境界が移動するので、
面の並びではなく形の変わり目に沿う。

    blender -b --factory-startup --python eval_proxy_region.py -- \
        [--tol 35] [--iters 8]
"""
from __future__ import annotations

import heapq
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


OUT = Path(arg("--out", str(HERE / "out" / "proxy_region"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "700"))
LEVELS = int(arg("--levels", "2"))
TOL = float(arg("--tol", "35"))
ITERS = int(arg("--iters", "8"))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def add_suzanne(applied):
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("Sub", type="SUBSURF")
    m.levels = m.render_levels = LEVELS
    if applied:
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o


def face_graph(topo):
    ok = topo.two_face
    a = topo.face_a[ok].astype(np.int64)
    b = topo.face_b[ok].astype(np.int64)
    src = np.concatenate([a, b])
    dst = np.concatenate([b, a])
    order = np.argsort(src, kind="stable")
    src, dst = src[order], dst[order]
    first = np.searchsorted(src, np.arange(topo.n_faces + 1))
    return dst, first


def grow_greedy(normals, dst, first, cos_tol):
    """先着順で育てる。領域の数と種を決めるためだけに使う。"""
    nf = len(normals)
    visited = np.zeros(nf, dtype=bool)
    seeds = []
    for s in range(nf):
        if visited[s]:
            continue
        visited[s] = True
        acc = normals[s].copy()
        mean = acc / max(np.linalg.norm(acc), 1e-12)
        queue = [s]
        while queue:
            f = queue.pop()
            for k in range(first[f], first[f + 1]):
                g = int(dst[k])
                if visited[g]:
                    continue
                n = normals[g]
                ln = np.linalg.norm(n)
                if ln < 1e-12 or float(np.dot(mean, n / ln)) < cos_tol:
                    continue
                visited[g] = True
                queue.append(g)
                acc += n
                mean = acc / max(np.linalg.norm(acc), 1e-12)
        seeds.append(s)
    return seeds


def assign_by_priority(normals, areas, dst, first, seeds, proxies):
    """代表法線とのズレが小さい面から順に取り込む。"""
    nf = len(normals)
    label = np.full(nf, -1, dtype=np.int32)
    heap = []
    for r, s in enumerate(seeds):
        label[s] = r
        for k in range(first[s], first[s + 1]):
            g = int(dst[k])
            cost = float(areas[g] * (1.0 - np.dot(normals[g], proxies[r])))
            heapq.heappush(heap, (cost, g, r))
    while heap:
        cost, f, r = heapq.heappop(heap)
        if label[f] >= 0:
            continue
        label[f] = r
        for k in range(first[f], first[f + 1]):
            g = int(dst[k])
            if label[g] >= 0:
                continue
            c = float(areas[g] * (1.0 - np.dot(normals[g], proxies[r])))
            heapq.heappush(heap, (c, g, r))
    # 取り残し(孤立した面)は自分だけの領域にする
    for f in np.flatnonzero(label < 0).tolist():
        label[f] = len(seeds)
        seeds.append(f)
        proxies = np.vstack([proxies, normals[f]])
    return label, proxies


def proxies_from(label, normals, areas, n_reg):
    """領域ごとの代表法線(面積で重みづけした平均)。"""
    acc = np.zeros((n_reg, 3), dtype=np.float64)
    np.add.at(acc, label, normals * areas[:, None])
    ln = np.linalg.norm(acc, axis=1)
    ln[ln < 1e-12] = 1.0
    return acc / ln[:, None]


def best_seeds(label, normals, proxies, n_reg):
    """各領域で代表法線にいちばん合う面を、次の種にする。"""
    fit = np.einsum("ij,ij->i", normals, proxies[label])
    seeds = [-1] * n_reg
    best = np.full(n_reg, -2.0)
    for f in range(len(normals)):
        r = int(label[f])
        if fit[f] > best[r]:
            best[r] = fit[f]
            seeds[r] = f
    return [s if s >= 0 else 0 for s in seeds]


def segment(topo, normals, areas, tol_deg, iters):
    dst, first = face_graph(topo)
    cos_tol = math.cos(math.radians(tol_deg))
    seeds = grow_greedy(normals, dst, first, cos_tol)
    proxies = normals[np.array(seeds, dtype=np.int64)].copy()
    label = None
    for _ in range(max(1, iters)):
        label, proxies = assign_by_priority(normals, areas, dst, first,
                                            seeds, proxies)
        n_reg = len(seeds)
        proxies = proxies_from(label, normals, areas, n_reg)
        seeds = best_seeds(label, normals, proxies, n_reg)
    n_reg = int(label.max()) + 1
    islands = [np.flatnonzero(label == r) for r in range(n_reg)]
    islands = [x for x in islands if len(x)]
    return islands


def paint_islands(o, islands, seed_int=42):
    from freepencil2 import utils, mesh_islands
    me = o.data
    nf = len(me.polygons)
    label = np.zeros(nf, dtype=np.int64)
    for i, faces in enumerate(islands):
        label[faces] = i
    topo = mesh_islands.MeshTopology(me)
    ok = topo.two_face
    la = label[topo.face_a[ok].astype(np.int64)]
    lb = label[topo.face_b[ok].astype(np.int64)]
    diff = la != lb
    nbrs = [set() for _ in islands]
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
    totals = np.zeros(nf, dtype=np.int64)
    me.polygons.foreach_get("loop_total", totals)
    idx = np.repeat(np.arange(nf), totals)
    buf = np.zeros(len(me.loops) * 4, dtype=np.float32)
    buf[0::4] = cols[idx, 0]
    buf[1::4] = cols[idx, 1]
    buf[2::4] = cols[idx, 2]
    buf[3::4] = 1.0
    attr.data.foreach_set("color", buf)
    me.color_attributes.active_color = attr
    return n_cls


def fit_cam(o):
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


def one(key, applied, tol, iters):
    from freepencil2 import mesh_islands, fp_core
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    o = add_suzanne(applied)
    me = o.data
    nf = len(me.polygons)
    normals = np.zeros(nf * 3, dtype=np.float32)
    me.polygons.foreach_get("normal", normals)
    normals = normals.reshape(nf, 3).astype(np.float64)
    ln = np.linalg.norm(normals, axis=1)
    ln[ln < 1e-12] = 1.0
    normals /= ln[:, None]
    areas = np.zeros(nf, dtype=np.float32)
    me.polygons.foreach_get("area", areas)
    areas = areas.astype(np.float64)

    topo = mesh_islands.MeshTopology(me)
    islands = segment(topo, normals, areas, tol, iters)
    n_cls = paint_islands(o, islands)

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

    fit_cam(o)
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{key}.png"
    fp_batch.render_still(scene, png, 1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    say(f"{key}: 面{nf:,} 島{len(islands)} 色{n_cls} "
        f"しきい値{tol}度 反復{iters}")
    return {"file": png.name, "faces": nf, "islands": len(islands)}


def main():
    fp_batch.install_addon()
    res = {}
    for tol in (25.0, 35.0, 45.0):
        for applied in (False, True):
            key = f"{'app' if applied else 'cage'}{tol:.0f}"
            try:
                res[key] = one(key, applied, tol, ITERS)
            except Exception as e:                       # noqa: BLE001
                say(f"{key}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
