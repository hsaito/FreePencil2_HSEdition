import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()
OUT = Path(__file__).resolve().parent / "out" / "t76"; OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_homefile(use_empty=True)
objs = []
bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.2, 0, 0.9)); objs.append(bpy.context.object)
bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0.8, 0.3, 0.6)); objs.append(bpy.context.object)
for i in range(4):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.8, -0.31, 0.2 + i * 0.28)); g = bpy.context.object; g.scale = (1.0, 0.02, 0.03); objs.append(g)
sc = bpy.context.scene
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -6, 1.6); cam.rotation_euler = (math.radians(82), 0, 0)
sc.render.resolution_x, sc.render.resolution_y = 320, 240
sc.render.film_transparent = (sys.argv[-1] == "T")
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"): setattr(sc, p_, False)
sc.fp_color_seed = 7; sc.fp_auto_style = "WEIGHTED"
bpy.ops.object.select_all(action="DESELECT")
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
for ft in (True, False):
    sc.render.film_transparent = ft
    sc.render.filepath = str(OUT / f"step0{sys.argv[-1]}_ft{int(ft)}.png"); bpy.ops.render.render(write_still=True)
