"""(既定は手描き背景)地面なしを STEP0 して、測った値と 透過/不透明 の絵を出す(旧コード/新コードの A/B 用)。
  -- <出力> [仕上がり] [保存する .blend]"""
import math, sys, json
from pathlib import Path
ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_monkey_add(size=1.8, location=(-1.1, 0, 0.9))
bpy.context.object.modifiers.new("S", "SUBSURF"); bpy.ops.object.shade_smooth()
bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -6, 0.8); cam.rotation_euler = (math.radians(86), 0, 0)
lt = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN")); sc.collection.objects.link(lt)
lt.rotation_euler = (math.radians(40), 0, math.radians(30))
sc.render.resolution_x, sc.render.resolution_y = 480, 270
sc.render.film_transparent = False
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    setattr(sc, p_, False)
sc.fp_color_seed = 5
for o in sc.objects:
    if o.type == "MESH": o.select_set(True)
bpy.context.view_layer.objects.active = sc.objects["Suzanne"]
sc.fp_auto_style = ARGV[1] if len(ARGV) > 1 else "BACKGROUND"
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
if len(ARGV) > 2:
    bpy.ops.wm.save_as_mainfile(filepath=ARGV[2])
m = {k: round(float(getattr(sc, k)), 5) for k in dir(sc) if k.startswith("fp_lw_e") or k in ("fp_lw_density", "fp_lw_far_start", "fp_lw_far_end")}
print("@@", json.dumps(m), flush=True)
for ft in (True, False):
    sc.render.film_transparent = ft
    sc.render.filepath = str(OUT / f"bg_ft{int(ft)}.png"); bpy.ops.render.render(write_still=True)
