"""町(STEP0 前)に精密の STEP0 を掛けて、指定フレームを低解像度で撮る(保存しない)。

  blender -b --factory-startup --python eval_town_precise_cap.py -- \
      --out out/raisecap/town_before [--raise-cap 85] [--frames 300,560]
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out")).resolve()
FRAMES = [int(v) for v in arg("--frames", "300,560").split(",")]
CAP = arg("--raise-cap")
STYLE = arg("--style", "PRECISE")

sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import shoot_town_v2 as st        # noqa: E402


def main():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(HERE / "out" / "town_v2" / "town_pre.blend"))
    sc = bpy.context.scene
    sc.fp_auto_style = STYLE
    if CAP is not None:
        sc["fp_raise_cap"] = float(CAP)
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = 'MONO_LIGHT'
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.eevee.taa_render_samples = 4
    st.FRAMES = 720
    st.moving_cars(sc)
    for f in FRAMES:
        st.aim(sc.camera, f)
        sc.frame_set(f + 1)
        fp_batch.render_still(sc, OUT / f"f{f:04d}.png", 1)
        print(f"@@@ f{f:04d}", flush=True)


if __name__ == "__main__":
    main()
