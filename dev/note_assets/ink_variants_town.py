"""町(手描き背景で STEP0 済み)で、線を薄くする既定値の候補を撮り比べる。白プレビューとモノクロの両方。

  blender -b --factory-startup --python ink_variants_town.py -- <town BACKGROUND.blend> <out> [--frames 250,700]
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
BLEND, OUT = Path(ARGV[0]), Path(ARGV[1])
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
FRAMES = [int(v) for v in arg("--frames", "250,700").split(",")]
HERE = Path(r"E:\10_cowork\00_code\22_FreePencil\dev\note_assets")
sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402
import shoot_town_v2 as st    # noqa: E402

import json
VARIANTS = json.loads(open(arg("--variants"), encoding="utf-8-sig").read()) if arg("--variants") else {
    "A_now":      dict(fp_lw_ink=0.75, fp_lw_dense=0.6, fp_lw_far_fade=0.35, fp_lw_stripe_fade=1.0),
    "C_ink1_d3":  dict(fp_lw_ink=1.0,  fp_lw_dense=0.3, fp_lw_far_fade=0.15, fp_lw_stripe_fade=1.0),
    "D_ink9_d3s5": dict(fp_lw_ink=0.9, fp_lw_dense=0.3, fp_lw_far_fade=0.15, fp_lw_stripe_fade=0.5),
}
fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
sc = bpy.context.scene
st.FRAMES = 720
st.moving_cars(sc)
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.eevee.taa_render_samples = 16
for vname, props in VARIANTS.items():
    for k, v in props.items():
        setattr(sc, k, v)
    for mode in ("WHITE", "MONO_LIGHT"):
        sc.fp_preview_mode = mode
        bpy.ops.freepencil2.link_button()
        for f in FRAMES:
            st.aim(sc.camera, f - 1)
            sc.frame_set(f)
            sc.render.filepath = str(OUT / f"{vname}_{mode}_f{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    print("@@@", vname, flush=True)
