"""ハイポリのなめらかな形は、島ではなく**法線の向き**で塗ってみる。

島で塗る方式は、色の境界が必ず面の縁を通る。だから面が粗いと輪郭が
カクカクになり、面が細かいと今度は格子を拾う。どちらも「面の粒」に
縛られているのが原因。

法線で塗れば粒から外れる。頂点ごとの法線から色を決めて角(コーナー)に
書けば、色は面の中で補間される。境界は面の縁ではなく**面の内側**を
通れるので、粗いメッシュでもなめらかな線になる。

3通り試す。

  auto   いまの自動(島で塗る)。比較用
  nrgb   オブジェクト空間の法線をそのまま色にする(n*0.5+0.5)。
         色は連続なので、Sobel が反応するのは法線が急に変わる所
         =曲率の高い稜線だけになるはず
  nq16   法線の向きを16方向に量子化してパレットを割り当てる。
         はっきりした段差ができるので線は確実に出るが、
         段の境目が形と無関係な場所に来る危険がある

ローポリ・メカは従来方式のままでよいはずなので、立方体も並べて
「法線方式だと壊れる形」を確かめる。判定は画像で行う(CLAUDE.md)。

    blender -b --factory-startup --python eval_normal_color.py -- [--levels 2]
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


OUT = Path(arg("--out", str(HERE / "out" / "normal_color"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
LEVELS = int(arg("--levels", "2"))
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


def torus():
    bpy.ops.mesh.primitive_torus_add(major_segments=48, minor_segments=24)
    return bpy.context.object


def sphere():
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32)
    return bpy.context.object


def cube():
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.object


SHAPES = [("スザンヌ(適用済み)", lambda: suzanne(True)),
          ("スザンヌ(ケージ)", lambda: suzanne(False)),
          ("トーラス", torus),
          ("UV球", sphere),
          ("立方体(ローポリ対照)", cube)]


# ---------------------------------------------------------------- 法線色
def corner_normals(mesh):
    """角ごとの法線。スムーズシェードなら頂点法線が補間されて入る。"""
    nl = len(mesh.loops)
    arr = np.empty(nl * 3, dtype=np.float32)
    try:
        mesh.corner_normals.foreach_get("vector", arr)
    except (AttributeError, RuntimeError):
        # 4.0 以前: 頂点法線を角へ引き写す
        lv = np.empty(nl, dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", lv)
        vn = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("normal", vn)
        arr = vn.reshape(-1, 3)[lv].ravel()
    n = arr.reshape(-1, 3).astype(np.float64)
    ln = np.linalg.norm(n, axis=1)
    ln[ln < 1e-12] = 1.0
    return n / ln[:, None]


def fib_dirs(k):
    """球面にだいたい等間隔な k 方向。量子化の代表点に使う。"""
    i = np.arange(k) + 0.5
    z = 1.0 - 2.0 * i / k
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = i * np.pi * (3.0 - np.sqrt(5.0))
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def write_colors(mesh, cols):
    attr = mesh.color_attributes.get("mecha_color")
    if attr is None:
        attr = mesh.color_attributes.new(name="mecha_color", type='BYTE_COLOR',
                                         domain='CORNER')
    buf = np.ones(len(mesh.loops) * 4, dtype=np.float32)
    buf[0::4] = cols[:, 0]
    buf[1::4] = cols[:, 1]
    buf[2::4] = cols[:, 2]
    attr.data.foreach_set("color", buf)
    mesh.color_attributes.active_color = attr


def paint_normal_rgb(obj):
    n = corner_normals(obj.data)
    write_colors(obj.data, (n * 0.5 + 0.5).astype(np.float32))
    return "法線そのまま"


def paint_normal_quant(obj, k, seed_int=42):
    from freepencil2 import utils
    n = corner_normals(obj.data)
    dirs = fib_dirs(k)
    bucket = np.argmax(n @ dirs.T, axis=1)
    pal, _d, _l = utils.palette_for_diversity(0.5, k, seed_int, min_k=k)
    pal = np.array(pal, dtype=np.float32)
    write_colors(obj.data, pal[bucket % len(pal)])
    return f"{k}方向に量子化(色{len(pal)})"


# ------------------------------------------------------------------ 撮影
def look(o, zoom=float(arg("--zoom", "1.7"))):
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


def one(tag, make, mode):
    from freepencil2 import fp_core
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    o = make()
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_preview_mode = 'NONE'
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_sharp = False
    sc.fp_sharp_auto = True
    sc.fp_curve_blur = 0

    if mode == "auto":
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        note = "島で塗る(従来)"
    else:
        # 法線を面の中で補間させたいのでスムーズシェードにする。
        # ただし "keep" 付きは元のシェーディングのまま(フラットなら
        # 面ごとに法線が違うので、立方体でも段差=線になるはず)
        bpy.context.view_layer.objects.active = o
        if not mode.endswith("keep"):
            bpy.ops.object.shade_smooth()
        note = (paint_normal_rgb(o) if mode.startswith("nrgb")
                else paint_normal_quant(o, int(mode[2:])))
        note += "" if not mode.endswith("keep") else " / シェーディングそのまま"
        if not o.material_slots:
            o.data.materials.append(bpy.data.materials.new("FP_Mat"))
        for s in o.material_slots:
            if s.material is None:
                s.material = bpy.data.materials.new("FP_Mat")
            s.material.use_nodes = True
        fp_core.setup_aov(sc, bpy.context.view_layer)
        fp_core.setup_compositor(sc, bpy.context.view_layer)

    look(o)
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    key = f"{tag}_{mode}"
    fp_batch.render_still(sc, OUT / f"{key}_line.png", 1)
    render_vc(sc, o, OUT / f"{key}_vc.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    say(f"{key}: 面{len(o.data.polygons):,}  {note}")
    return {"key": key, "mode": mode, "faces": len(o.data.polygons)}


MODES = [x for x in (arg("--modes", "auto,nrgb,nq16").split(","))]


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"m{i:02d}"
        for mode in MODES:
            try:
                r = one(tag, make, mode)
                r["label"] = label
                rows.append(r)
            except Exception as e:                       # noqa: BLE001
                import traceback
                traceback.print_exc()
                say(f"{tag}_{mode}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"levels": LEVELS, "rows": rows}, ensure_ascii=False,
                   indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
