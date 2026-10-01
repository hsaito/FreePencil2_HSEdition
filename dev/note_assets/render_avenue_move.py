"""大通りを飛ぶカットを撮る(STEP0 済みの avenue_bg.blend)。

  blender -b --factory-startup --python render_avenue_move.py -- --out out/avenue/fly1
      [--blend out/avenue/avenue_bg.blend] [--res 960] [--samples 4] [--frames 48]
      [--speed 1.0]   1 コマで進む距離(m)。24fps で 1.0 = 24 m/s
      [--y0 -120] [--z0 16] [--z1 16]   開始位置と、最初/最後の高さ(高さは滑らかに変える)
      [--sway 0.0]    左右のゆれ(m)
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "avenue" / "avenue_bg.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "avenue" / "fly"))).resolve()
RES = int(arg("--res", "960"))
SAMPLES = int(arg("--samples", "4"))
N = int(arg("--frames", "48"))
SPEED = float(arg("--speed", "1.0"))
Y0 = float(arg("--y0", "-120"))
Z0, Z1 = float(arg("--z0", "16")), float(arg("--z1", "16"))
SWAY = float(arg("--sway", "0.0"))
FAR = arg("--far")            # 「奥の線を控えめに」(0 で切る。省略 = STEP0 の値)
RELIEF = arg("--relief")      # 「つぶれ軽減」(同上)
ONLY = {int(v) for v in arg("--only", "").split(",") if v}
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402


def ease(t):
    return t * t * (3 - 2 * t)


fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
sc = bpy.context.scene
sc.render.resolution_x = RES
sc.render.resolution_y = RES * 9 // 16
sc.eevee.taa_render_samples = SAMPLES
if FAR is not None:
    sc.fp_lw_far_amount = float(FAR)
if RELIEF is not None:
    sc.fp_lw_relief = float(RELIEF)
cam = sc.camera
OUT.mkdir(parents=True, exist_ok=True)
for i in range(N):
    if ONLY and (i + 1) not in ONLY:
        continue
    t = i / max(1, N - 1)
    cam.location.y = Y0 + SPEED * i
    cam.location.z = Z0 + (Z1 - Z0) * ease(t)
    cam.location.x = SWAY * math.sin(t * math.pi * 2)
    sc.render.filepath = str(OUT / f"f{i + 1:04d}.png")
    bpy.ops.render.render(write_still=True)
print("@@@ done", N, flush=True)
