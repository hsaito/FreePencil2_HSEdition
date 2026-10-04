"""スザンヌで「サブディビあり」と「Apply済み」を一致させる案を全部試す。

基準: サブディビあり(ケージ500面 + モディファイア段数2)を通常の自動判定で描く。
これに Apply済み(7,872面)を一致させられるかを、3案で比べる。

  案1 ケージ復元   Un-Subdivide でケージへ戻し、サブディビを付け直してから塗る
  案2 距離で測る   辺の両側で「k面ぶん離れた面」の法線を比べる。k は物体サイズ
                   に対する一定距離を平均辺長で割って決めるので、面の細かさに
                   依存しない
  案3 領域で育てる 種から広げ、領域の平均法線とのズレで切る

判定は画像で行う。.blend も全部保存する。

    blender -b --factory-startup --python eval_match_all.py -- [--levels 2]
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


OUT = Path(arg("--out", str(HERE / "out" / "match_all"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "700"))
LEVELS = int(arg("--levels", "2"))
DIST = float(arg("--dist", "0.05"))     # 案2で見る距離(物体サイズ比)
TOL2 = float(arg("--tol2", "45"))       # 案2のしきい値
TOL3 = float(arg("--tol3", "35"))       # 案3のしきい値
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


def mesh_arrays(me):
    nf = len(me.polygons)
    normals = np.zeros(nf * 3, dtype=np.float32)
    me.polygons.foreach_get("normal", normals)
    centers = np.zeros(nf * 3, dtype=np.float32)
    me.polygons.foreach_get("center", centers)
    co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    ev = np.zeros(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    el = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    return (normals.reshape(nf, 3).astype(np.float64),
            centers.reshape(nf, 3).astype(np.float64),
            size, float(np.mean(el)) if len(el) else size)


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


def walk_away(start, avoid_dir, centers, dst, first, k):
    """start から avoid_dir と逆向きへ k 歩あるいた面を返す。"""
    cur = int(start)
    for _ in range(k):
        lo, hi = first[cur], first[cur + 1]
        if lo >= hi:
            break
        cand = dst[lo:hi]
        v = centers[cand] - centers[cur]
        ln = np.linalg.norm(v, axis=1)
        ln[ln < 1e-12] = 1.0
        score = (v / ln[:, None]) @ (-avoid_dir)
        cur = int(cand[int(np.argmax(score))])
    return cur


def islands_by_distance(topo, normals, centers, k, tol_deg):
    """案2: 辺の両側で k 面ぶん離れた面の法線を比べる。"""
    dst, first = face_graph(topo)
    ok = topo.two_face
    idx = np.flatnonzero(ok)
    fa = topo.face_a[ok].astype(np.int64)
    fb = topo.face_b[ok].astype(np.int64)
    cos_tol = math.cos(math.radians(tol_deg))
    b = np.ones(topo.n_edges, dtype=bool)
    keep = np.zeros(len(idx), dtype=bool)
    for i in range(len(idx)):
        a0, b0 = int(fa[i]), int(fb[i])
        d = centers[b0] - centers[a0]
        ln = float(np.linalg.norm(d))
        if ln < 1e-12:
            keep[i] = True
            continue
        d /= ln
        pa = walk_away(a0, d, centers, dst, first, k)
        pb = walk_away(b0, -d, centers, dst, first, k)
        na, nb = normals[pa], normals[pb]
        la, lb = np.linalg.norm(na), np.linalg.norm(nb)
        if la < 1e-12 or lb < 1e-12:
            keep[i] = True
            continue
        keep[i] = float(np.dot(na / la, nb / lb)) >= cos_tol
    b[idx] = ~keep
    topo.is_boundary = b
    topo.build_islands()
    return topo.islands


def islands_by_region(topo, normals, tol_deg):
    """案3: 領域の平均法線とのズレで育てる。"""
    nf = topo.n_faces
    dst, first = face_graph(topo)
    visited = np.zeros(nf, dtype=bool)
    cos_tol = math.cos(math.radians(tol_deg))
    islands = []
    for seed in range(nf):
        if visited[seed]:
            continue
        visited[seed] = True
        acc = normals[seed].copy()
        mean = acc / max(np.linalg.norm(acc), 1e-12)
        members, queue = [seed], [seed]
        while queue:
            f = queue.pop()
            for kk in range(first[f], first[f + 1]):
                g = int(dst[kk])
                if visited[g]:
                    continue
                n = normals[g]
                ln = np.linalg.norm(n)
                if ln < 1e-12 or float(np.dot(mean, n / ln)) < cos_tol:
                    continue
                visited[g] = True
                members.append(g)
                queue.append(g)
                acc += n
                mean = acc / max(np.linalg.norm(acc), 1e-12)
        islands.append(np.array(sorted(members), dtype=np.int64))
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


def finish(o, key, info):
    from freepencil2 import fp_core
    scene = bpy.context.scene
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
    png = OUT / f"{key}.png"
    fp_batch.render_still(scene, png, 1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    info["file"] = png.name
    say(f"{key}: " + " ".join(f"{k}={v}" for k, v in info.items()
                              if k != "file"))
    return info


def run_normal(key, applied):
    """通常の自動判定。基準と、Apply済みの素の結果。"""
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    o = add_suzanne(applied)
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False
    scene.fp_auto_sharp = False
    scene.fp_sharp_auto = True
    scene.fp_curve_blur = 0
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    return finish(o, key, {"faces": len(o.data.polygons)})


def run_unsubdiv(key):
    """案1: Apply済みをケージへ戻し、サブディビを付け直してから通常処理。"""
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    o = add_suzanne(True)
    before = len(o.data.polygons)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.unsubdivide(iterations=LEVELS)
    bpy.ops.object.mode_set(mode="OBJECT")
    after = len(o.data.polygons)
    m = o.modifiers.new("Sub", type="SUBSURF")
    m.levels = m.render_levels = LEVELS
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_auto_sharp = False
    scene.fp_sharp_auto = True
    scene.fp_curve_blur = 0
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    return finish(o, key, {"before": before, "cage": after})


def run_custom(key, applied, method):
    """案2 / 案3。島を自前で決めて塗る(STEP1 は通さない)。"""
    from freepencil2 import mesh_islands
    bpy.ops.wm.read_homefile(use_empty=True)
    o = add_suzanne(applied)
    me = o.data
    normals, centers, size, mean_edge = mesh_arrays(me)
    topo = mesh_islands.MeshTopology(me)
    if method == "dist":
        k = max(1, int(round(size * DIST / max(mean_edge, 1e-9))))
        islands = islands_by_distance(topo, normals, centers, k, TOL2)
        info = {"faces": len(me.polygons), "k": k, "islands": len(islands)}
    else:
        islands = islands_by_region(topo, normals, TOL3)
        info = {"faces": len(me.polygons), "islands": len(islands)}
    paint_islands(o, islands)
    return finish(o, key, info)


def main():
    fp_batch.install_addon()
    res = {}
    res["base_live"] = run_normal("base_live", False)
    res["plain_applied"] = run_normal("plain_applied", True)
    res["a1_unsubdiv"] = run_unsubdiv("a1_unsubdiv")
    res["a2_dist_cage"] = run_custom("a2_dist_cage", False, "dist")
    res["a2_dist_app"] = run_custom("a2_dist_app", True, "dist")
    res["a3_region_cage"] = run_custom("a3_region_cage", False, "region")
    res["a3_region_app"] = run_custom("a3_region_app", True, "region")
    (OUT / "index.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
