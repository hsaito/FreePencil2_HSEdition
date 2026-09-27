"""モノクロで輪郭の外に出る黒い帯を調べる。白/モノクロ x 強弱の強さ、透明地の有無で撮る。"""
import math, sys
from pathlib import Path
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_monkey_add(size=2); mk = bpy.context.object
mk.modifiers.new("S", "SUBSURF"); bpy.ops.object.shade_smooth()
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -6, 0.4); cam.rotation_euler = (math.radians(86), 0, 0)
lt = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN")); sc.collection.objects.link(lt)
lt.rotation_euler = (math.radians(40), 0, math.radians(30))
sc.render.resolution_x, sc.render.resolution_y = 480, 360
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    setattr(sc, p_, False)
sc.fp_auto_style = 'WEIGHTED'
bpy.ops.object.select_all(action="DESELECT"); mk.select_set(True); bpy.context.view_layer.objects.active = mk
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
print("@@ film_transparent", sc.render.film_transparent, "strength", sc.fp_lw_strength)
for mode in ("WHITE", "MONO_LIGHT"):
    sc.fp_preview_mode = mode
    for st in (0.6, 1.0):
        sc.fp_lw_strength = st
        for ft in (True, False):
            sc.render.film_transparent = ft
            sc.render.filepath = str(OUT / f"{mode}_s{st}_ft{int(ft)}.png")
            bpy.ops.render.render(write_still=True)
sc.fp_lw_strength = 0.6
sc.fp_line_weight = False
sc.render.film_transparent = True
sc.render.filepath = str(OUT / "MONO_LIGHT_noweight_ft1.png")
bpy.ops.render.render(write_still=True)
print("@@ done")
