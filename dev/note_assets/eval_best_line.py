"""土台の線を決めたうえで、仮想ライトの明るいところを細くする。

順番が大事。強弱は土台の線を太らせたり細らせたりするだけなので、
土台が途切れていれば強弱を付けても途切れたままになる。

土台(スザンヌ)は eval_base_line.py の掃き出しで決めた。
    まとめ率 0.3   1.0 だと目の虹彩の輪が消える。0.0 だと
                   メッシュの格子が眉にハッチングとして出る
    稜線     0.25  なめらかな額に眉の線を足す
    感度     0.25  0.35 以上だと頬の線が2値化で点線になる。
                   0.18 まで下げると目のまわりが塊になる
    2値化    0.15  0.25 だと薄い線を落としてしまう

強弱は、線の画素における陰影値の分位点で段に切る。分位点なので
解像度にも絵柄にも依らない。段ごとに太さを変え、最後に50%縮小。
一番細い段でも 2px 残すので、縮小しても線は切れない。

    python dev/note_assets/eval_best_line.py [--src out/baseline2] \
        [--line s025] [--levels 5,4,3,2,1] [--gain 1.4]
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent


def _mod(name: str, path: str):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")
bl = _mod("bl", "eval_binary_line.py")


def tiers(base: np.ndarray, shade: np.ndarray, levels: list[int]) -> np.ndarray:
    """線の画素だけを見て陰影を等分し、暗いほど太くする。

    分位点で切るので、段ごとの線の量がだいたい揃う。明るさの絶対値で
    切ると、絵によっては全部が同じ段に入って強弱が消える。
    """
    on = base > 0.5
    v = shade[on]
    n = len(levels)
    edges = [float(np.percentile(v, 100.0 * (k + 1) / n)) for k in range(n - 1)]
    # 段は「線そのものの位置の明るさ」で決める。太らせた後の画素で
    # 決めると、太らせた縁が別の段に入って切り落とされ、暗くて太い
    # はずの段が細くなる(実測: 5段の幅が 2.0/3.3/4.9/4.1/3.3px と
    # 山なりになり、一番太いはずの段が一番細かった)
    out = np.zeros_like(base)
    for k, px in enumerate(levels):
        lo = -1e9 if k == 0 else edges[k - 1]
        hi = 1e9 if k == n - 1 else edges[k]
        seg = base * ((shade >= lo) & (shade < hi))
        out = np.maximum(out, bl.morph(seg, px))
    return out


def widths(base: np.ndarray, shade: np.ndarray, levels: list[int]) -> list[float]:
    """段ごとの線幅(px)を、縮小後の値で返す。

    細長い帯では、距離変換の平均が幅の 1/4 になる。これを使う。
    面積÷芯の長さで測ろうとして 1.8倍 と出たことがあるが、
    芯の長さを縁の画素数から見積もったのが雑で、太い段ほど
    過大評価していた。距離変換なら段の形に依らない。
    """
    on = base > 0.5
    v = shade[on]
    n = len(levels)
    edges = [float(np.percentile(v, 100.0 * (k + 1) / n)) for k in range(n - 1)]
    out = []
    for k, px in enumerate(levels):
        lo = -1e9 if k == 0 else edges[k - 1]
        hi = 1e9 if k == n - 1 else edges[k]
        seg = base * ((shade >= lo) & (shade < hi))
        m = bl.morph(seg, px) > 0.5
        if m.sum() == 0:
            out.append(0.0)
            continue
        dt = ndimage.distance_transform_edt(m)
        out.append(float(dt[m].mean()) * 4.0 / 2.0)   # 4x = 幅、/2 = 縮小
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "baseline2"))
    ap.add_argument("--line", default="s025")
    ap.add_argument("--bin", type=float, default=0.15)
    ap.add_argument("--levels", default="5,4,3,2,1")
    ap.add_argument("--gain", type=float, default=1.4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    src = Path(a.src)
    levels = [int(x) for x in a.levels.split(",")]

    ink = 1.0 - mx.load(src / f"{a.line}.png")
    shade = mx.load(src / "shade.png")
    base = bl.binarize(ink, a.bin)

    lab, nc = ndimage.label(base > 0.5, structure=np.ones((3, 3)))
    sz = np.bincount(lab.ravel())[1:]
    print(f"土台  インク {base.mean() * 100:.3f}%  連結成分 {nc}"
          f" (200px超 {int((sz > 200).sum())})")

    flat = np.clip(bl.shrink(bl.morph(base, levels[len(levels) // 2])), 0, 1)
    out = tiers(base, shade, levels)
    v = np.clip(bl.shrink(out) * a.gain, 0.0, 1.0)

    lab2, nc2 = ndimage.label(v > 0.15, structure=np.ones((3, 3)))
    sz2 = np.bincount(lab2.ravel())[1:]
    w = widths(base, shade, levels)
    on = v > 0.15
    print(f"強弱後 連結成分 {nc2} (200px超 {int((sz2 > 200).sum())})")
    print("  段ごとの線幅 " + " / ".join(f"{x:.1f}px" for x in w)
          + f"   最太÷最細 {max(w) / max(min(w), 1e-9):.1f}倍")
    print(f"  真っ黒率(>0.85) {(v[on] > 0.85).mean() * 100:.1f}%"
          f"  平均濃度 {v[on].mean():.3f}")

    dst = Path(a.out) if a.out else src / "best.png"
    mx.to_img(v).save(dst)
    mx.to_img(flat).save(dst.with_name(dst.stem + "_flat.png"))
    print(f"\n{dst}\n{dst.with_name(dst.stem + '_flat.png')}")


if __name__ == "__main__":
    main()
