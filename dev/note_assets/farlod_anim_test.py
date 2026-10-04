"""遠い区画をまとめる: カメラが動くカットで、近づく先のビルが粗くならないか。

  blender -b --factory-startup --python farlod_anim_test.py -- <pre.blend> <out_dir> [--anim] [--no-farlod] [--dist 200]
カメラを 1〜200 コマで dist m 前進させる(--anim ならキーを打ってから STEP0、無しなら STEP0 の後に動かす)。
1 コマ目と 200 コマ目を白プレビューで撮る。
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
PRE, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
DIST = float(arg("--dist", "200"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
if "--no-farlod" in ARGV:
    _vc = sys.modules[next(m for m in sys.modules if m.endswith(".vertex_color"))]
    _vc.far_lod_cameras = lambda scene: None
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(PRE))
sc = bpy.context.scene
cam = sc.camera
y0 = cam.location.y
sc.frame_start, sc.frame_end = 1, 200
if "--anim" in ARGV:
    sc.frame_set(1)
    cam.location.y = y0
    cam.keyframe_insert("location", index=1, frame=1)
    cam.location.y = y0 + DIST
    cam.keyframe_insert("location", index=1, frame=200)
    sc.frame_set(1)
sc.fp_auto_style = "BACKGROUND"
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
sc.fp_preview_mode = "WHITE"
bpy.ops.freepencil2.link_button()
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.eevee.taa_render_samples = 16
for f in (1, 200):
    sc.frame_set(f)
    if "--anim" not in ARGV:
        cam.location.y = y0 + DIST * (f - 1) / 199.0
    sc.render.filepath = str(OUT / f"f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
print("@@@ done", flush=True)
