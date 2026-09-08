"""複数モデルのシーンで、外形の太さと陰影による太さを試す。

  外形  深度チャンネルを膨張させる。オブジェクトの外と重なりが太くなる
  陰影  仮想ライトで暗いところの線をさらに太くする。線画の定石

どちらも 2値のまま行い、最後に 50% 縮小する。灰色に薄めるのではなく
面積で太さを変えるのが要点(「かすれが甘い」のはそこだった)。

    python dev/note_assets/eval_scene_mix.py [--src out/scene]
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
_s1 = importlib.util.spec_from_file_location("mx", HERE / "eval_taper_mix.py")
mx = importlib.util.module_from_spec(_s1)
_s1.loader.exec_module(mx)
_s2 = importlib.util.spec_from_file_location("bl", HERE / "eval_binary_line.py")
bl = importlib.util.module_from_spec(_s2)
_s2.loader.exec_module(bl)


def weighted(dep, mec, shade, thresh=0.25, out_px=1, in_px=-1,
             dark=0.0, dark_at=0.55):
    """外形と内側の太さを変え、暗いところをさらに太らせる。

    dark は暗部で追加する膨張量(画素)。dark_at より暗いところに効かせる。
    陰影は面の明るさなので線そのものではない。線の位置での明るさを見る。
    """
    bd, bm = bl.binarize(dep, thresh), bl.binarize(mec, thresh)
    base = np.maximum(bl.morph(bd, out_px), bl.morph(bm, in_px))
    if dark <= 0:
        return bl.shrink(base)
    # 暗いところだけ、もう一段太らせたものに差し替える
    fat = bl.morph(base, int(round(dark)))
    m = (shade < dark_at).astype(np.float64)
    # 影の境目で段差が出ないよう、マスク自体も少しだけ広げる
    m = bl.morph(m, 1)
    return bl.shrink(np.where(m > 0.5, fat, base))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "scene"))
    ap.add_argument("--zoom", type=int, default=2)
    a = ap.parse_args()
    src = Path(a.src)

    all_ = 1.0 - mx.load(src / "ch_all.png")
    dep = 1.0 - mx.load(src / "ch_depth.png")
    mec = 1.0 - mx.load(src / "ch_mecha.png")
    shade = mx.load(src / "shade.png")
    print(f"陰影: 平均 {shade.mean():.3f}  0.55より暗い割合 {(shade < 0.55).mean():.3f}")

    trials = [
        ("いまの線", bl.shrink(all_)),
        ("外形+1 / 内側-1", weighted(dep, mec, shade)),
        ("+ 暗部を+1", weighted(dep, mec, shade, dark=1)),
        ("+ 暗部を+2", weighted(dep, mec, shade, dark=2)),
        ("外形+2 / 内側-1 + 暗部+1",
         weighted(dep, mec, shade, out_px=2, dark=1)),
        ("暗部だけ+1 (外形そのまま)",
         weighted(dep, mec, shade, out_px=0, in_px=0, dark=1)),
    ]

    print("\n  条件                        インク   いまの線比")
    base = trials[0][1].sum()
    tiles = []
    for name, v in trials:
        v = np.clip(v, 0.0, 1.0)
        print(f"  {name:<26} {v.mean():.5f}  {v.sum() / base * 100:6.1f}%")
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
    dst = src / "scene_weight.png"
    s.save(dst)
    print(f"\n{dst}")


if __name__ == "__main__":
    main()
