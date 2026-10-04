"""手描き背景の「線を薄くする」既定値の候補を、同じ STEP0 済みの .blend で撮り比べる(白プレビュー)。

  blender -b --factory-startup --python ink_variants.py -- <background.blend> <out> [--views near,aerial] [--cam name:x:y:z:pitch:yaw ...]
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
BLEND, OUT = Path(ARGV[0]), Path(ARGV[1])
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
sys.path.insert(0, r"E:\10_cowork\00_code\22_FreePencil\dev\batch")
import bpy, fp_batch          # noqa: E402

import json
VARIANTS = json.loads(open(arg("--variants"), encoding="utf-8-sig").read()) if arg("--variants") else {
    "A_now":      dict(fp_lw_ink=0.75, fp_lw_dense=0.6, fp_lw_far_fade=0.35, fp_lw_stripe_fade=1.0),
    "B_ink1":     dict(fp_lw_ink=1.0,  fp_lw_dense=0.6, fp_lw_far_fade=0.35, fp_lw_stripe_fade=1.0),
    "C_ink1_d3":  dict(fp_lw_ink=1.0,  fp_lw_dense=0.3, fp_lw_far_fade=0.15, fp_lw_stripe_fade=1.0),
    "D_ink9_d3s5": dict(fp_lw_ink=0.9, fp_lw_dense=0.3, fp_lw_far_fade=0.15, fp_lw_stripe_fade=0.5),
}
CAMS = {}
for spec in (arg("--cams") or "near:-21.5:-60:2.5:91:0,aerial:-3.5:34:16.2:74:0").split(","):
    n, *v = spec.split(":")
    CAMS[n] = tuple(float(x) for x in v)

fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)
for vname, props in VARIANTS.items():
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    sc.fp_preview_mode = "WHITE"
    for k, v in props.items():
        setattr(sc, k, v)
    bpy.ops.freepencil2.link_button()                # STEP3 を作り直して確実に反映
    if arg("--shift0"):
        sc.camera.data.shift_y = 0.0
    sc.render.resolution_x, sc.render.resolution_y = int(arg("--res", "1920")), int(arg("--res", "1920")) * 9 // 16
    sc.eevee.taa_render_samples = 16
    cam = sc.camera
    if arg("--lens"):
        cam.data.lens = float(arg("--lens"))
    for cname, (x, y, z, p, yw) in CAMS.items():
        cam.location = (x, y, z)
        cam.rotation_euler = (math.radians(p), 0, math.radians(yw))
        sc.render.filepath = str(OUT / f"{vname}_{cname}.png")
        bpy.ops.render.render(write_still=True)
    print("@@@", vname, flush=True)
