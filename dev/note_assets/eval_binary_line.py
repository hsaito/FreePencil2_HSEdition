"""線を2値化してから太さを変え、50%縮小で仕上げる実験。

これまでの合成は、内側の線に 0.6 を掛けて薄くしていた。これは
「細くなった」のではなく「灰色になった」だけで、かすれて見える。

線画は本来ベタ塗り。太さは面積で決まる。そこで

    1. 等倍で撮った線を 2値化する (芯はベタ黒)
    2. 2値のまま膨張・侵食で太さを変える
       外形 = 膨張、内側 = 侵食
    3. 50% に縮小する。縁の階調は面積平均から出る

の順で作る。侵食は等倍で 1px = 縮小後 0.5px なので、細くしても
線が千切れない。前回、縮小後の絵を侵食して汚くなったのはこのため。

    python dev/note_assets/eval_binary_line.py [--src out/hi_car]
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("mx", HERE / "eval_taper_mix.py")
mx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mx)


def binarize(ink: np.ndarray, t: float) -> np.ndarray:
    return (ink > t).astype(np.float64)


def morph(mask: np.ndarray, px: int) -> np.ndarray:
    """px>0 で膨張、px<0 で侵食。2値のまま太さだけ変える。"""
    if px == 0:
        return mask
    im = Image.fromarray((mask * 255).astype(np.uint8))
    k = 2 * abs(px) + 1
    im = im.filter(ImageFilter.MaxFilter(k) if px > 0
                   else ImageFilter.MinFilter(k))
    return np.asarray(im, dtype=np.float64) / 255.0


def shrink(ink: np.ndarray, factor: int = 2) -> np.ndarray:
    """面積平均で縮小する。ここで初めて中間調が出る。"""
    h, w = ink.shape
    h2, w2 = h // factor * factor, w // factor * factor
    v = ink[:h2, :w2].reshape(h2 // factor, factor, w2 // factor, factor)
    return v.mean(axis=(1, 3))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "hi_car"))
    ap.add_argument("--thresh", type=float, default=0.25)
    ap.add_argument("--zoom", type=int, default=2)
    a = ap.parse_args()
    src = Path(a.src)

    all_ = 1.0 - mx.load(src / "ch_all.png")
    dep = 1.0 - mx.load(src / "ch_depth.png")
    mec = 1.0 - mx.load(src / "ch_mecha.png")
    t = a.thresh

    bd, bm = binarize(dep, t), binarize(mec, t)
    print(f"2値化しきい値 {t}: 深度 {bd.mean():.5f} / メカ {bm.mean():.5f}")

    trials = [
        ("元の線 (等倍を縮小しただけ)", shrink(all_)),
        ("2値化のみ", shrink(np.maximum(bd, bm))),
        ("外形+1 / 内側-1", shrink(np.maximum(morph(bd, 1), morph(bm, -1)))),
        ("外形+2 / 内側-1", shrink(np.maximum(morph(bd, 2), morph(bm, -1)))),
        ("外形+2 / 内側-2", shrink(np.maximum(morph(bd, 2), morph(bm, -2)))),
        ("外形+3 / 内側-1", shrink(np.maximum(morph(bd, 3), morph(bm, -1)))),
    ]

    print("\n  条件                          インク   元比")
    base = trials[0][1].sum()
    tiles = []
    for name, v in trials:
        v = np.clip(v, 0.0, 1.0)
        print(f"  {name:<28} {v.mean():.5f}  {v.sum() / base * 100:5.1f}%")
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
    dst = src / "binary_line.png"
    s.save(dst)
    print(f"\n{dst}")


if __name__ == "__main__":
    main()
