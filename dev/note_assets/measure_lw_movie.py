"""デモ動画のキャプションに載せる数字を、その動画の素材から測る。

前の動画は別の撮影で測った数字をキャプションに書いていた。既定値を
変えて撮り直したので、数字も同じ素材から出し直す。定義は前と同じ:

    真っ黒率        濃さ>0.15 の画素のうち >0.85 の割合(eval_best_line)
    隣接フレーム差  インク総量の隣り合うフレーム間の変化率の平均(eval_ao_mix)

  python dev/note_assets/measure_lw_movie.py [--src out/lw_movie6] [--step 10]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


def ink_of(p: Path) -> np.ndarray:
    im = Image.open(p).convert("RGBA")
    a = np.asarray(im, dtype=np.float32) / 255.0
    # 白地に載せてから濃さにする。透明は白
    rgb = a[..., :3] * a[..., 3:4] + (1.0 - a[..., 3:4])
    return 1.0 - rgb.mean(axis=2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "lw_movie6"))
    ap.add_argument("--step", type=int, default=10)
    a = ap.parse_args()
    src = Path(a.src)
    out = {}
    for kind in ("off", "on"):
        files = sorted((src / kind).glob("f*.png"))
        if not files:
            raise SystemExit(f"素材が無い: {src / kind}")
        black = []
        totals = []
        for i, p in enumerate(files):
            v = ink_of(p)
            totals.append(float(v.sum()))
            if i % a.step == 0:
                on = v > 0.15
                black.append(float((v[on] > 0.85).mean()) if on.any() else 0.0)
        t = np.array(totals)
        step = np.abs(np.diff(t)) / np.maximum(t[:-1], 1e-9) * 100.0
        out[kind] = {"frames": len(files),
                     "black_rate": round(float(np.mean(black)) * 100, 1),
                     "step_mean": round(float(step.mean()), 2),
                     "step_max": round(float(step.max()), 2),
                     "ink_mean": round(float(t.mean()), 0)}
        print(f"{kind:<4} {len(files)}枚  真っ黒率 {out[kind]['black_rate']:.1f}%  "
              f"隣接フレーム差 平均 {out[kind]['step_mean']:.2f}% "
              f"最大 {out[kind]['step_max']:.2f}%")
    (src / "stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    print(src / "stats.json")


if __name__ == "__main__":
    main()
