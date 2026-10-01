"""STEP0 済みの canyon2_bg.blend で、レンズ(焦点距離)を変えて OFF / ON を 4K で撮り比べる。

  blender -b --factory-startup --python canyon2_lens.py -- --lens 50,70,100 [--y -60] [--out out/canyon2/lens]
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "canyon2" / "canyon2_bg.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "canyon2" / "lens"))).resolve()
LENSES = [float(v) for v in arg("--lens", "50,70,100").split(",")]
Y = float(arg("--y", "-60"))
RES = int(arg("--res", "1920"))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
sc = bpy.context.scene
sc.render.resolution_x = RES
sc.render.resolution_y = RES * 9 // 16
sc.eevee.taa_render_samples = 8
cam = sc.camera
cam.location.y = Y
for lens in LENSES:
    cam.data.lens = lens
    for tag, (far, relief) in (("on", (0.0, 1.0)), ("off", (0.0, 0.0))):
        sc.fp_lw_far_amount = far
        sc.fp_lw_relief = relief
        sc.render.filepath = str(OUT / f"l{int(lens)}_{tag}.png")
        bpy.ops.render.render(write_still=True)
        print(f"@@@ lens {lens} {tag}", flush=True)
