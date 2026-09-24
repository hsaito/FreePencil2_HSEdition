"""密度の高い町で「つぶれ軽減」の効き方を比べる(STEP3 だけ作り直して撮る)。

  none     つぶれ軽減なし(奥の扱い 0 / 線を減らす 1 / 薄く 0 / 遠景のつぶれ軽減 0)
  cur      手描き背景の既定(奥ほど細く 1.0・減らす 2.0・薄く 0.35)
  weak     奥の扱いを弱める(0.6・1.5・0.2)
  strong   強める(1.0・3.0・0.5)
  relief   既定 + 遠景のつぶれ軽減 0.6(混み具合で間引く、v2.6 の機能)
  fine0    既定から細い線 0
  fine1    既定から細い線 1.0

  blender -b --factory-startup --python eval_crush_relief.py -- \
      [--blend out/town_v4/town.blend] [--frames 250,450,700] [--out out/town_v4/crush]
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "town_v4" / "town.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "town_v4" / "crush"))).resolve()
FRAMES = [int(v) for v in arg("--frames", "250,450,700").split(",")]
ONLY = [v for v in arg("--variants", "").split(",") if v]

sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import shoot_town_v2 as st        # noqa: E402

VARIANTS = {
    "none":   dict(fp_lw_far=0.0, fp_lw_far_sens=1.0, fp_lw_far_fade=0.0, fp_far_relief=0.0),
    "cur":    dict(),
    "weak":   dict(fp_lw_far=0.6, fp_lw_far_sens=1.5, fp_lw_far_fade=0.2),
    "strong": dict(fp_lw_far=1.0, fp_lw_far_sens=3.0, fp_lw_far_fade=0.5),
    "relief": dict(fp_far_relief=0.6),
    "fine0":  dict(fp_fine_lines=0.0),
    "fine1":  dict(fp_fine_lines=1.0),
    "d0":     dict(fp_lw_dense=0.0),
    "d04":    dict(fp_lw_dense=0.4),
    "d06":    dict(fp_lw_dense=0.6),
    "d08":    dict(fp_lw_dense=0.8),
    "d10":    dict(fp_lw_dense=1.0),
    "s0":     dict(fp_lw_stripe_fade=0.0),
    "s1":     dict(fp_lw_stripe_fade=1.0),
}


def main():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    res = int(arg("--res", "1280"))
    sc.render.resolution_x, sc.render.resolution_y = res, res * 9 // 16
    sc.eevee.taa_render_samples = int(arg("--samples", "4"))
    st.FRAMES = 720
    st.moving_cars(sc)
    base = {k: getattr(sc, k) for v in VARIANTS.values() for k in v if hasattr(sc, k)}
    for name, vals in VARIANTS.items():
        if ONLY and name not in ONLY:
            continue
        for k, v in base.items():
            setattr(sc, k, v)
        for k, v in vals.items():
            setattr(sc, k, v)
        bpy.ops.freepencil2.link_button()
        for f in FRAMES:
            st.aim(sc.camera, f)
            sc.frame_set(f + 1)
            fp_batch.render_still(sc, OUT / f"f{f:04d}_{name}.png", 1)
            print(f"@@@ {name} f{f}", flush=True)


if __name__ == "__main__":
    main()
