"""「サブディビジョン付き・未適用の60度」と同じ絵を、他の条件でも出せるか。

サブディビジョン付き・未適用のトーラスとスザンヌは、自動しきい値が60度を
返して良い絵になった。一方、Apply して焼き込んだ場合は自動が5〜21度まで
落ちてメッシュの格子が線になる。

ではしきい値を60度に固定すれば、どの条件でも同じ絵になるのか。
これを確かめる。同じ形を3条件 × 2通り(自動 / 60度固定)で並べる。

    blender -b --factory-startup --python eval_threshold60.py -- [--levels 2]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "threshold60"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "700"))
LEVELS = int(arg("--levels", "2"))
FIX = float(arg("--fix", "60.0"))
T0 = time.time()

SHAPES = [
    ("トーラス", lambda: (bpy.ops.mesh.primitive_torus_add(),
                      bpy.context.object)[1]),
    ("スザンヌ", lambda: (bpy.ops.mesh.primitive_monkey_add(),
                      bpy.context.object)[1]),
    ("UV球", lambda: (bpy.ops.mesh.primitive_uv_sphere_add(),
                     bpy.context.object)[1]),
    ("円柱", lambda: (bpy.ops.mesh.primitive_cylinder_add(),
                    bpy.context.object)[1]),
]

CONDS = [("none", "サブディビジョン無し"),
         ("live", "付けたまま(未適用)"),
         ("applied", "Apply 済み")]

MODES = [("auto", "自動"), ("fix", f"{FIX:.0f}度固定")]


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


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


def one(tag, make, cond, mode):
    from freepencil2 import mesh_islands, utils
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    o = make()
    if cond != "none":
        m = o.modifiers.new("Sub", type="SUBSURF")
        m.levels = m.render_levels = LEVELS
        if cond == "applied":
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.modifier_apply(modifier=m.name)

    has_sub = any(md.type == 'SUBSURF' and md.show_viewport
                  for md in o.modifiers)
    if mode == "auto":
        topo = mesh_islands.MeshTopology(o.data)
        deg, _m = utils.choose_auto_threshold(
            topo.angle_samples_deg(), has_subsurf=has_sub)
    else:
        deg = FIX

    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False
    scene.fp_auto_sharp = False
    scene.fp_curve_blur = 0
    scene.fp_sharp_auto = (mode == "auto")
    if mode != "auto":
        scene.fp_sharp_edges = FIX

    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    fit(o)
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{tag}_{cond}_{mode}.png"
    fp_batch.render_still(scene, png, 1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{tag}_{cond}_{mode}.blend"))
    return {"file": png.name, "deg": round(deg, 1),
            "base_faces": len(o.data.polygons)}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"t{i:02d}"
        shots = {}
        for ck, _cl in CONDS:
            for mk, _ml in MODES:
                try:
                    shots[f"{ck}_{mk}"] = one(tag, make, ck, mk)
                except Exception as e:                   # noqa: BLE001
                    say(f"{label} {ck}/{mk}: 失敗 {e}")
        rows.append({"label": label, "tag": tag, "shots": shots})
        say(f"{label:<10} " + " / ".join(
            f"{k}:{v['deg']:.0f}度" for k, v in shots.items()))
    (OUT / "index.json").write_text(
        json.dumps({"fix": FIX, "conds": CONDS, "modes": MODES, "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
