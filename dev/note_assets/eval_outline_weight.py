"""外形を太く、内側を細くする実験。画像の上で試す。

eval_taper_ch.py が撮った

    ch_depth.png   深度チャンネルだけ = 外形と重なり
    ch_mecha.png   メカチャンネルだけ = 内側の塗り分け
    ch_all.png     全部 (比較用)

を使う。深度が外形をきれいに出していることは目で確認済み
(車は車体のシルエットと屋根のレールだけ、内側の細部は入らない)。

    外形 = 深度を膨らませる (太くする)
    内側 = メカを弱める (細く見せる)
    出力 = 濃い方を採る

入り抜き(曲率マスク)が有機物でしか成立しなかったのに対し、こちらは
チャンネルがそのまま外形と内側に対応しているので、モデルの性質に
依存しない見込み。

    python dev/note_assets/eval_outline_weight.py [--src out/ch_car]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
import importlib.util                                   # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "mx", HERE / "eval_taper_mix.py")
mx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mx)


def dilate(ink: np.ndarray, px: int) -> np.ndarray:
    """インクを膨らませて線を太くする。0 なら何もしない。"""
    if px <= 0:
        return ink
    im = Image.fromarray((np.clip(ink, 0, 1) * 255).astype(np.uint8))
    # MaxFilter のサイズは奇数。1px 太らせるなら 3
    im = im.filter(ImageFilter.MaxFilter(2 * px + 1))
    return np.asarray(im, dtype=np.float64) / 255.0


def erode(ink: np.ndarray, px: int) -> np.ndarray:
    if px <= 0:
        return ink
    im = Image.fromarray((np.clip(ink, 0, 1) * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MinFilter(2 * px + 1))
    return np.asarray(im, dtype=np.float64) / 255.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "ch_car"))
    ap.add_argument("--zoom", type=int, default=2)
    a = ap.parse_args()
    src = Path(a.src)

    all_ = 1.0 - mx.load(src / "ch_all.png")
    dep = 1.0 - mx.load(src / "ch_depth.png")
    mec = 1.0 - mx.load(src / "ch_mecha.png")

    trials = [
        ("元の線", all_),
        ("外形+1px / 内側 x0.60", np.maximum(dilate(dep, 1), mec * 0.60)),
        ("外形+1px / 内側 x0.40", np.maximum(dilate(dep, 1), mec * 0.40)),
        ("外形+2px / 内側 x0.40", np.maximum(dilate(dep, 2), mec * 0.40)),
        ("外形+2px / 内側 細らせ", np.maximum(dilate(dep, 2), erode(mec, 1))),
        ("外形+2px / 内側 細+x0.7",
         np.maximum(dilate(dep, 2), erode(mec, 1) * 0.7)),
    ]

    print("  条件                        インク  元比")
    base = all_.sum()
    tiles = []
    for name, v in trials:
        v = np.clip(v, 0.0, 1.0)
        print(f"  {name:<26} {v.sum() / v.size:.5f}  {v.sum() / base * 100:5.1f}%")
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
    dst = src / "outline_weight.png"
    s.save(dst)
    print(f"\n{dst}")


if __name__ == "__main__":
    main()
