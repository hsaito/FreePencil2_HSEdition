"""人だけのテスト場。手前から奥へ人を並べ、手描き背景/キャラで線を撮る。

  デッサン人形 x3(歩き。手前 5m・中 14m・奥 30m)、anime-girl(ジョギング)、
  man_01 / mozo(リグ付き)、stylized-male / standing-cool-bald(リグなし)。
  地面あり、モノクロの陰影。町と同じ条件で、人の線だけを見る。

  blender -b --factory-startup --python test_humans.py -- \
      [--style BACKGROUND] [--frames 1,7,13] [--out out/humans/cur] [--res 1280]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
STYLE = arg("--style", "BACKGROUND")
FRAMES = [int(v) for v in arg("--frames", "1,7,13").split(",")]
OUT = Path(arg("--out", str(HERE / "out" / "humans" / "cur"))).resolve()
RES = int(arg("--res", "1280"))

sys.argv = ["blender", "--", "--no-step0"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402
import make_town_demo as td       # noqa: E402
import make_town_v2 as tv         # noqa: E402  (load_doll: ミラー実体化・ノーマルマップ外し)
import dessin_walk                # noqa: E402

# (名前, x, y, 身長, 向き(度))。カメラは原点から +y を見る
PEOPLE = (
    ("doll", -1.5, 5.0, None, 20.0),
    ("anime-girl_2K", 1.6, 6.0, 1.6, -15.0),
    ("man_01", -3.6, 10.0, 1.75, 15.0),
    ("mozo_2K", 3.6, 10.5, 1.8, -20.0),
    ("doll", 0.0, 13.0, None, 60.0),
    ("stylized-male", -6.8, 17.0, 1.75, 10.0),
    ("standing-cool-bald", 6.8, 17.0, 1.8, -10.0),
    ("doll", -1.5, 28.0, None, -60.0),
)


def put_asset(pat, x, y, height, rot):
    objs = td.load_lot(pat)
    meshes = [o for o in objs if o.type == "MESH" and not o.hide_render]
    bb = td.bounds(meshes)
    s = height / max((bb[1] - bb[0]).z, 1e-6)
    ctr = (bb[0] + bb[1]) / 2
    m = (Matrix.Translation(Vector((x, y, 0))) @ Matrix.Rotation(math.radians(rot), 4, "Z")
         @ Matrix.Scale(s, 4) @ Matrix.Translation(Vector((-ctr.x, -ctr.y, -bb[0].z))))
    td.transform(objs, m)
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is not None and pat.startswith("anime-girl") and "Jogging" in bpy.data.actions:
        arm.animation_data_create()
        act = bpy.data.actions["Jogging"]
        arm.animation_data.action = act
        for fc in act.fcurves:
            if not any(md.type == "CYCLES" for md in fc.modifiers):
                fc.modifiers.new("CYCLES")
    return meshes


def put_doll(x, y, rot):
    grp, rig, meshes = tv.load_doll()
    grp.location = (x, y, 0.0)
    grp.rotation_euler = (0.0, 0.0, math.radians(rot))
    dessin_walk.make_walk(rig, name=f"Walk_{len(bpy.data.actions)}")
    return meshes


def main():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    meshes = []
    for name, x, y, h, rot in PEOPLE:
        meshes += put_doll(x, y, rot) if name == "doll" else put_asset(name, x, y, h, rot)
    bpy.ops.mesh.primitive_plane_add(size=1)
    ground = bpy.context.object
    ground.scale = (200, 200, 1)
    ground.location = (0, 40, 0)
    ground.name = "FP_ground"
    cd = bpy.data.cameras.new("C")
    cd.lens = 35.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.0, -1.5, 1.6)
    cam.rotation_euler = (Vector((0, 14, 1.0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.objects.new("K", bpy.data.lights.new("K", type="SUN"))
    lt.data.energy = 3.0
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(50), 0, math.radians(-35))
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 8
    sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.frame_set(FRAMES[0])
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes + [ground]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    sc.fp_auto_style = STYLE
    if arg("--side") is not None:          # 左右の明るさ: off / limbs / all(試験)
        sc["fp_side_tone_mode"] = arg("--side")
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = 'MONO_LIGHT'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "humans.blend"))
    for f in FRAMES:
        sc.frame_set(f)
        fp_batch.render_still(sc, OUT / f"f{f:02d}.png", 1)
        print(f"@@@ f{f}", flush=True)
    print(f"@@@ 完了 {OUT}", flush=True)


if __name__ == "__main__":
    main()
