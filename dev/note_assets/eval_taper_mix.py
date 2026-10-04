"""入り抜きの合成を、画像の上で試す。ノードを組む前の見極め。

eval_taper.py が撮った

    line.png   線画 (白地に黒線)
    point.png  凸の尖り具合
    conc.png   凹の尖り具合

を使い、線の濃さを曲率で変える式を何通りか試して並べる。

考え方: 折れているところは線が濃く、平らになるにつれて消える。
稜線が死んでいく端で線が細く消えれば、それが入り抜きになる。

    python dev/note_assets/eval_taper_mix.py [--src out/taper]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc",
         r"C:\Windows\Fonts\msgothic.ttc"]


def font(size: int):
    for p in FONTS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def load(p: Path) -> np.ndarray:
    """白地に合成してから輝度を 0..1 で返す。"""
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("L")
    return np.asarray(im, dtype=np.float64) / 255.0


def to_img(ink: np.ndarray) -> Image.Image:
    """インク量(0..1)を白地の絵に戻す。"""
    return Image.fromarray(
        (np.clip(1.0 - ink, 0.0, 1.0) * 255).astype(np.uint8)).convert("RGB")


def smoothstep(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / max(b - a, 1e-6), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "taper"))
    a = ap.parse_args()
    src = Path(a.src)

    line = load(src / "line.png")
    # マスクは「明るいほど尖っている」で撮ってある。輝度がそのまま強さ。
    # ただし背景は白(=1.0)なので、被写体の外も最大値になってしまう。
    # 線のある場所だけを見るので実害は無いが、値の意味は「面の上でのみ有効」
    point = load(src / "point.png")
    conc = load(src / "conc.png")

    ink = 1.0 - line                      # 線のあるところが 1
    curv = np.maximum(point, conc)        # 凸でも凹でも「折れている」量

    trials = [
        ("元の線", ink),
        ("凸だけ", ink * point),
        ("凹だけ", ink * conc),
        ("曲率(凸と凹の大きい方)", ink * curv),
        ("曲率を強調 0.05-0.45", ink * smoothstep(curv, 0.05, 0.45)),
        ("曲率を強調 0.10-0.60", ink * smoothstep(curv, 0.10, 0.60)),
        ("下限を残す 0.35+0.65x", ink * (0.35 + 0.65 * smoothstep(curv, 0.05, 0.45))),
        ("下限を残す 0.55+0.45x", ink * (0.55 + 0.45 * smoothstep(curv, 0.05, 0.45))),
    ]

    print("           式                              残ったインク  元比")
    base = ink.sum()
    out = []
    for name, v in trials:
        v = np.clip(v, 0.0, 1.0)
        print(f"  {name:<28} {v.sum() / v.size:.5f}   {v.sum() / base * 100:5.1f}%")
        out.append((name, to_img(v)))

    w, h = 640, 360
    cols = 4
    rows = (len(out) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 6) + 6, rows * (h + 34) + 6),
                      (150, 150, 156))
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(out):
        x, y = 6 + (i % cols) * (w + 6), 6 + (i // cols) * (h + 34)
        sheet.paste(im.resize((w, h)), (x, y))
        d.text((x + 6, y + h + 6), name, font=font(20), fill=(20, 20, 22))
    dst = src / "mix_sheet.png"
    sheet.save(dst)
    print(f"\n{dst}")


if __name__ == "__main__":
    main()
