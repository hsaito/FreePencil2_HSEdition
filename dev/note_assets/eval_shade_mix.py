"""陰影の境目を線にして、いまの線に足す。画像の上で試す。

やること:
    1. 陰影を段に切る (明部 / 中間 / 暗部)
    2. 段の境目を線として取り出す
    3. いまの線に足す

球で確かめたいのは3点。
    ・境目の線が1本きれいに出るか
    ・しきい値を変えると線がどこへ動くか
    ・段を2つにすると線が2本になるか

線は太さを持つので、境目は「段のマスクを膨らませて元との差を取る」形で
作る。こうすると幅が px 単位で決まり、他の線と同じ扱いにできる。

    python dev/note_assets/eval_shade_mix.py [--src out/shade_sph]
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def _mod(name: str, path: str):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")
bl = _mod("bl", "eval_binary_line.py")


def band_edge(shade: np.ndarray, thresh: float, width: int = 1,
              alpha: np.ndarray | None = None) -> np.ndarray:
    """明暗の段の境目を、指定した太さの線にして返す。

    段のマスクを膨らませて元との差を取る。こうすると線の幅が px で
    決まるので、いまの線と同じ土俵で足したり引いたりできる。
    被写体の外(alpha=0)には出さない。物の輪郭と二重になるため。
    """
    dark = (shade < thresh).astype(np.float64)
    if alpha is not None:
        dark = dark * alpha
    fat = bl.morph(dark, width)
    edge = np.clip(fat - dark, 0.0, 1.0)
    if alpha is not None:
        edge = edge * alpha
    return edge


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "shade_sph"))
    ap.add_argument("--zoom", type=float, default=1.0)
    a = ap.parse_args()
    src = Path(a.src)

    ink = 1.0 - mx.load(src / "line.png")
    shade = mx.load(src / "shade.png")
    # 被写体の内側だけを対象にする
    al = np.asarray(Image.open(src / "shade.png").convert("RGBA"),
                    dtype=np.float64)[..., 3] / 255.0
    inside = (al > 0.5).astype(np.float64)
    b = bl.binarize(ink, 0.25)
    print(f"線の画素 {int((b > 0.5).sum())}  被写体 {inside.mean() * 100:.1f}%")
    v = shade[inside > 0.5]
    print("  陰影の分布 " + " ".join(
        f"{p}%={np.percentile(v, p):.3f}" for p in (5, 25, 50, 75, 95)))

    trials = [("いまの線", bl.shrink(ink))]
    for th in (0.35, 0.50, 0.65):
        e = band_edge(shade, th, 1, inside)
        trials.append((f"境目 1本 しきい値{th:.2f}",
                       bl.shrink(np.maximum(b, e))))
    # 2段 = ターミネータ + 影の芯
    e2 = np.maximum(band_edge(shade, 0.55, 1, inside),
                    band_edge(shade, 0.28, 1, inside))
    trials.append(("境目 2本 0.55と0.28", bl.shrink(np.maximum(b, e2))))
    # 太さ2px
    trials.append(("境目 1本 0.50 を2px",
                   bl.shrink(np.maximum(b, band_edge(shade, 0.50, 2, inside)))))

    print("\n  条件                        インク   元比")
    base = trials[0][1].sum()
    tiles = []
    for name, x in trials:
        x = np.clip(x, 0.0, 1.0)
        print(f"  {name:<26} {x.mean():.5f}  {x.sum() / base * 100:6.1f}%")
        im = mx.to_img(x)
        if a.zoom != 1.0:
            im = im.resize((round(im.width * a.zoom), round(im.height * a.zoom)),
                           Image.LANCZOS)
        tiles.append((name, im))

    w, h = tiles[0][1].size
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    s = Image.new("RGB", (cols * (w + 6) + 6, rows * (h + 30) + 6),
                  (150, 150, 156))
    d = ImageDraw.Draw(s)
    for i, (n, im) in enumerate(tiles):
        x0, y0 = 6 + (i % cols) * (w + 6), 6 + (i // cols) * (h + 30)
        s.paste(im, (x0, y0))
        d.text((x0 + 6, y0 + h + 4), n, font=mx.font(22), fill=(20, 20, 22))
    dst = src / "shade_line.png"
    s.save(dst)
    print(f"\n{dst}")


if __name__ == "__main__":
    main()
