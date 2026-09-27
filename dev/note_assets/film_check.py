"""背景の透過(film_transparent)で線が変わるかを、3つの仕上がりで撮る。STEP0 は背景を不透明にしたまま押す。"""
import sys
from pathlib import Path
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()
for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
    bpy.ops.wm.open_mainfile(filepath=r"E:\10_cowork\00_code\22_FreePencil\dev\batch\out\audit\f452\base.blend")
    sc = bpy.context.scene
    sc.render.film_transparent = False            # Blender の既定
    ms = [o for o in sc.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    sc.fp_auto_style = style
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    print("@@", style, "film after STEP0:", sc.render.film_transparent, flush=True)
    for ft in (False, True):
        sc.render.film_transparent = ft
        sc.render.filepath = str(OUT / f"{style}_ft{int(ft)}.png")
        bpy.ops.render.render(write_still=True)
