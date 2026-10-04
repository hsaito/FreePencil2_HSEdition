"""リグ付きキャラを動かして、キャラ(手描き)の線とボーンの塗りを撮る。

anime-girl の Mixamo モーション(Jogging、その場で27フレーム)を4周させ、
カメラを 90 度回り込ませる。STEP0 は1フレーム目で1回だけ掛ける(実際の
使い方と同じ)。線画と、ボーンの塗り(bone_color を素通し)を並べた動画に
する。関節で切れ目の線が出ないか、動いても線が安定するかを見る。

  blender -b --factory-startup --python test_char_motion.py -- \
      [--model anime-girl_2K] [--action Jogging] [--loops 4] [--preview]
      [--only-frames 1,40] [--out out/char_motion]
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
MODEL = arg("--model", "anime-girl_2K")
ACTION = arg("--action", "Jogging")
LOOPS = int(arg("--loops", "4"))
PREVIEW = "--preview" in ARGV
RES = int(arg("--res", "960" if PREVIEW else "1920"))
SAMPLES = int(arg("--samples", "4" if PREVIEW else "16"))
ONLY = [int(v) for v in arg("--only-frames", "").split(",") if v]
OUT = Path(arg("--out", str(HERE / "out" / "char_motion"))).resolve()
FPS = 24

sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)


def setup():
    models = json.load(open(HERE.parent / "batch" / "out" / "models.json", encoding="utf-8"))
    m = next(x for x in models if MODEL in Path(x["path"]).stem)
    bpy.ops.wm.open_mainfile(filepath=m["path"])
    sc = bpy.context.scene
    arm = next(o for o in sc.objects if o.type == "ARMATURE")
    act = bpy.data.actions[ACTION]
    arm.animation_data_create()
    arm.animation_data.action = act
    f0, f1 = map(int, act.frame_range)
    for fc in act.fcurves:                     # 周期で回す
        if not any(md.type == "CYCLES" for md in fc.modifiers):
            fc.modifiers.new("CYCLES")
    n = (f1 - f0) * LOOPS
    sc.frame_start, sc.frame_end = f0, f0 + n - 1
    sc.render.fps = FPS

    meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render
              and len(o.data.polygons) > 0]
    # カメラ: 正面(-y)から 30 度で始めて 90 度回り込む。胸の高さを見る
    cd = bpy.data.cameras.new("C")
    cd.lens = 50.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tgt = Vector((0.0, 0.0, float(arg("--tgt-z", "0.82"))))
    d = float(arg("--dist", "4.8"))
    for f in range(sc.frame_start, sc.frame_end + 1):
        s = (f - sc.frame_start) / max(1, n - 1)
        e = 0.5 - 0.5 * math.cos(s * math.pi)
        a = math.radians(-30.0 + 90.0 * e)
        cam.location = (tgt.x + math.sin(a) * d, tgt.y - math.cos(a) * d, tgt.z + 0.35)
        cam.rotation_euler = (tgt - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    lt = bpy.data.objects.new("K", bpy.data.lights.new("K", type="SUN"))
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(50), 0, math.radians(-35))

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = SAMPLES
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.frame_set(sc.frame_start)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    sc.fp_auto_style = arg("--style", 'WEIGHTED')
    if "--side-tone" in ARGV:               # ボーンの明るさを左右で分ける(実験)
        sc["fp_bone_side_tone"] = True
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    if "--mono" in ARGV:
        sc.fp_mono_floor = 0.55
        sc.fp_preview_mode = 'MONO_LIGHT'
    print(f"@@@ STEP0 done: {len(meshes)} meshes, frames {sc.frame_start}-{sc.frame_end}, "
          f"bone_aov={sc.fp_bone_color}", flush=True)
    return sc, meshes


def bone_material():
    m = bpy.data.materials.new("look_bone")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = "GEOMETRY"
    a.attribute_name = "bone_color"
    e = nt.nodes.new("ShaderNodeEmission")
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(a.outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
    return m


def render(sc, sub, frames=None):
    d = OUT / sub
    d.mkdir(parents=True, exist_ok=True)
    if frames:
        for f in frames:
            sc.frame_set(f)
            sc.render.filepath = str(d / f"f{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    else:
        sc.render.filepath = str(d / "f")
        bpy.ops.render.render(animation=True)
    print(f"@@@ rendered {sub}", flush=True)


def main():
    fp_batch.install_addon()
    sc, meshes = setup()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "char_motion.blend"))
    render(sc, "line", ONLY)
    if "--line-only" in ARGV:              # デモ用: 線画だけ
        print("@@@ 完了", flush=True)
        return
    # ボーンの塗りを素通しで(コンポジタを切り、材質を差し替える)
    mat = bone_material()
    for o in meshes:
        for ms in o.material_slots:
            ms.link = "OBJECT"
            ms.material = mat
    sc.render.use_compositing = False
    sc.render.film_transparent = False
    sc.eevee.taa_render_samples = 1
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "Standard"
    render(sc, "bone", ONLY)
    print("@@@ 完了", flush=True)


if __name__ == "__main__":
    main()
