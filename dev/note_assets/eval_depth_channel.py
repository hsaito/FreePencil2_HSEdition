"""深度チャンネル(fp_ch_depth)を振って、人の重なりの線と町の地平線の帯を見る。

  blender -b --factory-startup --python eval_depth_channel.py -- --blend <file> --tag <name>
      [--frames 1] [--values 0,0.3,0.6,1.0] [--town]
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
FRAMES = [int(v) for v in arg("--frames", "1").split(",")]
VALUES = [float(v) for v in arg("--values", "0,0.3,0.6,1.0").split(",")]
OUT = Path(arg("--out", str(HERE / "out" / "depth_ch"))).resolve()
TOWN = "--town" in ARGV

sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402


def main():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.eevee.taa_render_samples = 4
    if TOWN:
        import shoot_town_v2 as st
        st.FRAMES = 720
        st.moving_cars(sc)
    for v in VALUES:
        sc.fp_ch_depth = v
        if "--relink" in ARGV:             # スライダーの即時反映ではなく STEP3 を作り直す
            bpy.ops.freepencil2.link_button()
        for f in FRAMES:
            if TOWN:
                st.aim(sc.camera, f)
                sc.frame_set(f + 1)
            else:
                sc.frame_set(f)
            fp_batch.render_still(sc, OUT / f"{TAG}_f{f:04d}_d{v:g}.png", 1)
            print(f"@@@ {TAG} f{f} depth {v:g}", flush=True)


if __name__ == "__main__":
    main()
