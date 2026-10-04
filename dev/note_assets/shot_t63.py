"""t63 の場面(細い板を詰めた長い壁を低い視点から)を 縞を薄く 0 / 1 で撮る。
  blender -b --python shot_t63.py -- --w 960 --h 540
"""
import math
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
W, H = int(arg("--w", 960)), int(arg("--h", 540))
OUT = Path(__file__).resolve().parent / "out" / "t63"

bpy.ops.wm.read_homefile(use_empty=True)
objs = []
for i in range(40):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(3.0, 30.0, 0.2 + i * 0.08))
    o = bpy.context.object
    o.scale = (0.05, 60.0, 0.04)
    objs.append(o)
bpy.ops.mesh.primitive_cube_add(size=1, location=(3.3, 30.0, 1.8))
o = bpy.context.object
o.scale = (0.2, 60.0, 3.6)
objs.append(o)
scene = bpy.context.scene
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
cam.data.lens = 24
cam.location = (0.0, -2.0, 1.6)
cam.rotation_euler = (math.radians(88), 0, math.radians(-8))
scene.collection.objects.link(cam)
scene.camera = cam
scene.fp_use_random_seed = False
scene.fp_color_seed = 7
scene.fp_enable_compositor_view = False
scene.fp_auto_detect_aov = False
scene.fp_auto_style = 'BACKGROUND'
scene.render.resolution_x = W
scene.render.resolution_y = H
scene.render.film_transparent = True
for o in objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
scene.fp_white_preview = True
for v in (0.0, 1.0):
    scene.fp_lw_stripe_fade = v
    scene.render.filepath = str(OUT / f"t63_{W}_{int(v)}.png")
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"t63_{W}.blend"))
