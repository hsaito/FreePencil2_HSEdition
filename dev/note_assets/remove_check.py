"""「FreePencil を外す」を絵で確かめる: STEP0 の前 / STEP0 の後 / 保存して開き直して外した後。

  blender -b --factory-startup --python remove_check.py -- <out_dir>
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.0, 0, 0.9))
bpy.ops.object.shade_smooth()
monkey = bpy.context.object
red = bpy.data.materials.new("Red")
red.use_nodes = True
red.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.1, 0.08, 1)
monkey.data.materials.append(red)
bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
cube = bpy.context.object
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 2, 0))
ground = bpy.context.object
blue = bpy.data.materials.new("Blue")
blue.use_nodes = True
blue.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.25, 0.7, 1)
ground.data.materials.append(blue)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
cam.location = (0, -6, 1.8)
cam.rotation_euler = (math.radians(80), 0, 0)
sc.collection.objects.link(cam)
sc.camera = cam
lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
lt.data.energy = 4
lt.rotation_euler = (math.radians(45), 0, math.radians(30))
sc.collection.objects.link(lt)
sc.render.resolution_x, sc.render.resolution_y = 640, 360
sc.eevee.taa_render_samples = 16


def shot(name):
    sc = bpy.context.scene
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", name, sc.view_settings.view_transform, sc.render.resolution_percentage,
          sc.render.film_transparent, flush=True)


shot("1_before")
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    setattr(sc, p_, False)
sc.fp_auto_style = "WEIGHTED"
bpy.ops.object.select_all(action="DESELECT")
for o in (monkey, cube, ground):
    o.select_set(True)
bpy.context.view_layer.objects.active = monkey
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
shot("2_after_step0")
blend = OUT / "check.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
bpy.ops.wm.open_mainfile(filepath=str(blend))
print("@@@ remove", bpy.ops.freepencil.remove(), flush=True)
shot("3_after_remove")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "removed.blend"))
