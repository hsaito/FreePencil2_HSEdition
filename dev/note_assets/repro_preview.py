"""プレビュー(マテリアル / 白 / モノクロ)の切り替えを、パネルと同じ操作で撮る。

スザンヌに灰色のツヤのある材質を付けて STEP0(キャラ)を押し、種類を切り替え、
途中で強弱のスライダー(STEP3 をその場で作り直す)を動かす。手順ごとに F12 を撮る。

  blender -b --factory-startup --python repro_preview.py -- [--out out/preview_bug/<tag>]
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "preview_bug" / "now"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_monkey_add(size=2)
mk = bpy.context.object
bpy.ops.object.modifier_add(type="SUBSURF")
bpy.ops.object.shade_smooth()
m = bpy.data.materials.new("grey_gloss")
m.use_nodes = True
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.08, 0.08, 0.08, 1)
b.inputs["Roughness"].default_value = 0.15
mk.data.materials.append(m)
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.location = (0, -6, 0.4)
cam.rotation_euler = (math.radians(86), 0, 0)
lt = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN"))
sc.collection.objects.link(lt)
lt.rotation_euler = (math.radians(40), 0, math.radians(30))
sc.render.resolution_x, sc.render.resolution_y = 480, 360
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    setattr(sc, p_, False)
sc.fp_auto_style = 'WEIGHTED'
bpy.ops.object.select_all(action="DESELECT")
mk.select_set(True)
bpy.context.view_layer.objects.active = mk

log = []


def shot(tag):
    sc.render.filepath = str(OUT / f"{len(log):02d}_{tag}.png")
    bpy.ops.render.render(write_still=True)
    log.append(f"{len(log):02d}_{tag}: mode={sc.fp_preview_mode} white_flag={sc.fp_white_preview}")
    print("@@@", log[-1], flush=True)


bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
shot("step0")
sc.fp_preview_mode = 'NONE'          # パネルの「マテリアル」
shot("material")
sc.fp_lw_ink = 0.9                   # マテリアルのままスライダー
shot("material_after_slider")
sc.fp_preview_mode = 'WHITE'         # パネルの「白」
shot("white")
sc.fp_lw_strength = 0.93             # スライダーを動かす(STEP3 がその場で作り直される)
shot("white_after_slider")
sc.fp_preview_mode = 'MONO_LIGHT'
shot("mono")
sc.fp_lw_soften = 4.0
shot("mono_after_slider")
sc.fp_preview_mode = 'WHITE'
shot("white_again")
bpy.ops.freepencil2.link_button()    # STEP3 を押し直す
shot("white_after_step3")
(OUT / "log.txt").write_text("\n".join(log), encoding="utf-8")
