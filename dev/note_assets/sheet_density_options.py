"""eval_density_options.py の結果を 1 枚に並べる(白背景、モデルの範囲で切り出し)。

  python sheet_density_options.py [--dir out/density_options]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ARGV = sys.argv[1:]
DIR = Path(ARGV[ARGV.index("--dir") + 1]) if "--dir" in ARGV else HERE / "out" / "density_options"
COLS = [("precise", "精密(参考)"), ("cur", "今の手描き背景"),
        ("ab", "案AB 細い線=本当の精密 0.6"), ("abc", "案ABC +奥の線減らし 2.0")]
FONT = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 22)
CELL = 560


def on_white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB"), im.getchannel("A").getbbox()


def model_rows():
    names = sorted({p.name.rsplit("_", 1)[0] for p in DIR.glob("*_cur.png")
                    if not p.name.startswith("town")})
    rows = []
    for n in names:
        ims, box = [], None
        for key, _ in COLS:
            p = DIR / f"{n}_{key}.png"
            if not p.exists():
                ims.append(None)
                continue
            im, bb = on_white(p)
            ims.append(im)
            if bb:
                box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]),
                                              max(box[2], bb[2]), max(box[3], bb[3]))
        pad = 20
        box = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
        cells = []
        for im in ims:
            if im is None:
                cells.append(None)
                continue
            c = im.crop(box)
            c.thumbnail((CELL, CELL), Image.LANCZOS)
            cells.append(c)
        rows.append((n.strip("_"), cells))
    return rows


def town_rows():
    rows = []
    for p in sorted(DIR.glob("town*_cur.png")):
        f = p.name.split("_")[0]
        cells = [None]
        for key, _ in COLS[1:]:
            q = DIR / f"{f}_{key}.png"
            if q.exists():
                im = on_white(q)[0]
                im.thumbnail((CELL, CELL), Image.LANCZOS)
                cells.append(im)
            else:
                cells.append(None)
        rows.append((f, cells))
    return rows


def build(rows, out):
    hs = [max(c.height for c in cells if c) for _, cells in rows]
    W = CELL * len(COLS) + 10 * (len(COLS) + 1)
    H = 40 + sum(h + 34 for h in hs)
    s = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(s)
    for i, (_, label) in enumerate(COLS):
        d.text((10 + i * (CELL + 10), 8), label, fill=(0, 0, 0), font=FONT)
    y = 40
    for (name, cells), h in zip(rows, hs):
        d.text((10, y + 2), name[:40], fill=(90, 90, 90), font=FONT)
        for i, c in enumerate(cells):
            if c is not None:
                s.paste(c, (10 + i * (CELL + 10), y + 32))
        y += h + 34
    s.save(out)
    print(out)


if __name__ == "__main__":
    mr = model_rows()
    if mr:
        build(mr, DIR / "sheet_models.png")
    tr = town_rows()
    if tr:
        build(tr, DIR / "sheet_town.png")
