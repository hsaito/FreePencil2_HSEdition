"""STEP0 済みの .blend を、白プレビューにしてそのままのカメラで撮る(設定は触らない)。

  blender -b --factory-startup --python render_white.py -- <in.blend> <out.png> [--res 1920] [--samples 16] [--mode WHITE]
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(Path(ARGV[0]).resolve()))
sc = bpy.context.scene
sc.fp_preview_mode = arg("--mode", "WHITE")
for kv in (arg("--set") or "").split(","):     # 試す値: --set fp_lw_far_sens=3,fp_lw_far=1
    if kv:
        k, v = kv.split("=")
        setattr(sc, k, float(v))
bpy.ops.freepencil2.link_button()
res = int(arg("--res", "1920"))
sc.render.resolution_x, sc.render.resolution_y = res, res * 9 // 16
sc.eevee.taa_render_samples = int(arg("--samples", "16"))
sc.render.filepath = str(Path(ARGV[1]).resolve())
bpy.ops.render.render(write_still=True)
print("@@@ white", ARGV[1], flush=True)
