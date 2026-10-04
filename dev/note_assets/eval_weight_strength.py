"""キャラ線画の「強弱の強さ」を振って並べる(STEP0 済みの .blend を開いて STEP3 だけ作り直す)。

  blender -b --factory-startup --python eval_weight_strength.py -- \
      --blend <file> --tag <name> [--frame 1] [--values 1.0,0.7,0.5,0.3]
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend")).resolve()
TAG = arg("--tag", BLEND.stem)
FRAME = int(arg("--frame", "1"))
VALUES = [float(v) for v in arg("--values", "1.0,0.7,0.5,0.3").split(",")]
OUT = Path(arg("--out", str(HERE / "out" / "weight_strength"))).resolve()
RES = int(arg("--res", "960"))

sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402


def main():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    sc.frame_set(FRAME)
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.eevee.taa_render_samples = 8
    for v in VALUES:
        sc.fp_lw_strength = v
        bpy.ops.freepencil2.link_button()
        sc.fp_white_preview = True
        fp_batch.render_still(sc, OUT / f"{TAG}_s{v:g}.png", 1)
        print(f"@@@ {TAG} strength {v:g}", flush=True)


if __name__ == "__main__":
    main()
