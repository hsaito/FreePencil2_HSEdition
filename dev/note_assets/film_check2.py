"""背景の透過で線が変わらないかを見る。地面あり(base.blend)/なし x 3つの仕上がり x 背景 不透明/透過、キャラはモノクロも。"""
import math, sys
from pathlib import Path
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()


def no_ground():
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


for scene_name in ("noground", "ground"):
    for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
        if scene_name == "ground":
            bpy.ops.wm.open_mainfile(filepath=r"E:\10_cowork\00_code\22_FreePencil\dev\batch\out\audit\f452\base.blend")
            bpy.context.scene.render.film_transparent = False
        else:
            no_ground()
        sc = bpy.context.scene
        ms = [o for o in sc.objects if o.type == "MESH"]
        bpy.ops.object.select_all(action="DESELECT")
        for o in ms: o.select_set(True)
        bpy.context.view_layer.objects.active = ms[0]
        sc.fp_auto_style = style
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        for ft in (False, True):
            sc.render.film_transparent = ft
            sc.render.filepath = str(OUT / f"{scene_name}_{style}_ft{int(ft)}.png")
            bpy.ops.render.render(write_still=True)
        if style == "WEIGHTED":
            sc.fp_preview_mode = "MONO_LIGHT"
            for ft in (False, True):
                sc.render.film_transparent = ft
                sc.render.filepath = str(OUT / f"{scene_name}_{style}_mono_ft{int(ft)}.png")
                bpy.ops.render.render(write_still=True)
        print("@@", scene_name, style, flush=True)
