"""「自然な線」モードの実験。要素を1つにまとめて効かせる。

つまみを並べるのではなく、1つのモードとして最も自然な絵を出したい。
中でやることは3つ。

  1. ベタ塗りにする
     等倍で 2値化してから 50% に縮小する。Sobel の出力をそのまま
     縮小すると最初から中間調で、線が眠くなる (実測: 2値化するだけで
     インクが車 +7.7% / スザンヌ +25.1%)。

  2. 外形を太く、内側を細く
     深度チャンネルが外形と重なりを、メカチャンネルが内側を作る。
     2値のまま膨張(+1)と侵食(-1)で太さを変える。侵食は -1 が限界で、
     -2 にすると車のボンネットの線が千切れた。

  3. 入り抜き
     曲率が低いところほど 2値化のしきい値を上げる。薄い灰色にするので
     はなく「消える」ので、ベタ塗りのまま線の端が抜ける。
     内側の線にだけ効かせる。外形に効かせると輪郭が破線になる
     (曲率マスクを全体に掛けたときに実際そうなった)。

    python dev/note_assets/eval_natural.py [--src out/hi_car]
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("mx", HERE / "eval_taper_mix.py")
mx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mx)
_spec2 = importlib.util.spec_from_file_location(
    "bl", HERE / "eval_binary_line.py")
bl = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(bl)


def natural(dep, mec, curv, thresh=0.25, out_px=1, in_px=-1, taper=0.0):
    """自然な線を1枚作る。taper=0 で入り抜きなし。"""
    # 外形はしきい値を動かさない。輪郭が途切れると形が壊れる
    bd = bl.binarize(dep, thresh)
    # 内側は曲率が低いほど条件を厳しくする = 端から消える
    tm = thresh + taper * (1.0 - np.clip(curv, 0.0, 1.0))
    bm = (mec > tm).astype(np.float64)
    return bl.shrink(np.maximum(bl.morph(bd, out_px), bl.morph(bm, in_px)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "hi_car"))
    ap.add_argument("--zoom", type=int, default=2)
    a = ap.parse_args()
    src = Path(a.src)

    all_ = 1.0 - mx.load(src / "ch_all.png")
    dep = 1.0 - mx.load(src / "ch_depth.png")
    mec = 1.0 - mx.load(src / "ch_mecha.png")
    curv = np.maximum(mx.load(src / "point.png"), mx.load(src / "conc.png"))

    trials = [
        ("いまの線", bl.shrink(all_)),
        ("自然 (入り抜きなし)", natural(dep, mec, curv, taper=0.0)),
        ("自然 + 入り抜き 0.10", natural(dep, mec, curv, taper=0.10)),
        ("自然 + 入り抜き 0.20", natural(dep, mec, curv, taper=0.20)),
        ("自然 + 入り抜き 0.35", natural(dep, mec, curv, taper=0.35)),
        ("自然 + 入り抜き 0.50", natural(dep, mec, curv, taper=0.50)),
    ]

    print("  条件                      インク    いまの線比")
    base = trials[0][1].sum()
    tiles = []
    for name, v in trials:
        v = np.clip(v, 0.0, 1.0)
        print(f"  {name:<24} {v.mean():.5f}  {v.sum() / base * 100:6.1f}%")
        im = mx.to_img(v)
        if a.zoom > 1:
            im = im.resize((im.width * a.zoom, im.height * a.zoom),
                           Image.NEAREST)
        tiles.append((name, im))

    w, h = tiles[0][1].size
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    s = Image.new("RGB", (cols * (w + 6) + 6, rows * (h + 32) + 6),
                  (150, 150, 156))
    d = ImageDraw.Draw(s)
    for i, (n, im) in enumerate(tiles):
        x, y = 6 + (i % cols) * (w + 6), 6 + (i // cols) * (h + 32)
        s.paste(im, (x, y))
        d.text((x + 6, y + h + 6), n, font=mx.font(24), fill=(20, 20, 22))
    dst = src / "natural.png"
    s.save(dst)
    print(f"\n{dst}")


if __name__ == "__main__":
    main()
