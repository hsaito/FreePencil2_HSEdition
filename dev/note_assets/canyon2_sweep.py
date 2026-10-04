"""STEP0 済みの canyon2_bg.blend で、つぶれ軽減の成分を切り分けて 4K で撮り比べる。

  blender -b --factory-startup --python canyon2_sweep.py -- [--blend out/canyon2/canyon2_bg.blend] [--out out/canyon2/sweep]
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "canyon2" / "canyon2_bg.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "canyon2" / "sweep"))).resolve()
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
sc = bpy.context.scene
print("@@@ start", {k: round(float(getattr(sc, k)), 3) for k in
                    ("fp_lw_relief", "fp_lw_far_amount", "fp_lw_dense", "fp_lw_stripe_fade",
                     "fp_lw_far", "fp_lw_far_sens", "fp_lw_far_fade", "fp_lw_strength", "fp_fine_lines")}, flush=True)
CASES = {
    "A_default": dict(fp_lw_relief=1.0, fp_lw_far_amount=1.0),
    "B_relief05": dict(fp_lw_relief=0.5, fp_lw_far_amount=1.0),
    "C_no_stripe": dict(fp_lw_relief=1.0, fp_lw_far_amount=1.0, fp_lw_stripe_fade=0.0),
    "D_far_only": dict(fp_lw_relief=0.0, fp_lw_far_amount=1.0),
    "E_relief_only": dict(fp_lw_relief=1.0, fp_lw_far_amount=0.0),
    "F_off": dict(fp_lw_relief=0.0, fp_lw_far_amount=0.0),
}
for name, props in CASES.items():
    for k, v in props.items():
        setattr(sc, k, v)
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"@@@ {name}", flush=True)
