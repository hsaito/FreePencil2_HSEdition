"""向きがばらばらな詰まった塊(茂み)が 縞を薄く で薄くならないか撮る(t63 の後半)。
  blender -b --python shot_bush.py -- [--old]   --old は向きの項を外した版
"""
import math
import random
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import fp_batch                                                    # noqa: E402
fp_batch.install_addon()

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(__file__).resolve().parent / "out" / "t63"
OUT.mkdir(parents=True, exist_ok=True)
import importlib                                                    # noqa: E402
lw = importlib.import_module(next(m for m in sys.modules if m.endswith(".line_weight")))
if "--old" in ARGV:
    lw.STRIPE_H0, lw.STRIPE_H1 = -1.0, 0.0


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    rnd = random.Random(3)
    objs = []
    for i in range(900):                                   # 茂み: 細い棒を向きばらばらに
        bpy.ops.mesh.primitive_cube_add(size=1, location=(
            rnd.uniform(-1.5, 1.5), 12 + rnd.uniform(-1.5, 1.5), 1.5 + rnd.uniform(-1.2, 1.2)))
        o = bpy.context.object
        o.scale = (0.02, 0.18, 0.02)
        o.rotation_euler = (rnd.uniform(0, math.pi), rnd.uniform(0, math.pi), rnd.uniform(0, math.pi))
        objs.append(o)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 40, 2))  # 奥の壁(奥度の幅を作る)
    o = bpy.context.object
    o.scale = (20, 0.2, 4)
    objs.append(o)
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 35
    cam.location = (0.0, -2.0, 1.6)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 7
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_auto_style = 'BACKGROUND'
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.film_transparent = True
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    scene.fp_white_preview = True
    return scene


sc = build()
tag = "old" if "--old" in ARGV else "new"
for v in (0.0, 1.0):
    sc.fp_lw_stripe_fade = v
    sc.render.filepath = str(OUT / f"bush_{tag}_{int(v)}.png")
    bpy.ops.render.render(write_still=True)
