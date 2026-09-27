"""2 つのフォルダの同じ名前の PNG を左右に並べる(版をまたいだ比較用)。差の大きい順。

  python compare_dirs.py <左のフォルダ> <右のフォルダ> <出力.png> [--labels 4.5,5.2] [--width 640]

差の数値(目に見えて変わった画素の割合)は並べる順に使うだけ。判定は絵で見る。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
A, B, OUT = Path(ARGV[0]), Path(ARGV[1]), Path(ARGV[2])
LA, LB = arg("--labels", "A,B").split(",")
W = int(arg("--width", "640"))
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 16)


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


rows = []
for pa in sorted(A.glob("*.png")):
    pb = B / pa.name
    if not pb.exists() or "_mecha" in pa.stem:
        continue
    x, y = white(pa), white(pb)
    if x.size != y.size:
        y = y.resize(x.size)
    d = float((np.abs(np.asarray(x.convert("L"), np.float32) - np.asarray(y.convert("L"), np.float32)) > 24).mean() * 100)
    rows.append((d, pa.name, x, y))
rows.sort(key=lambda r: -r[0])
if not rows:
    sys.exit("比べる画像が無い(同じ名前の PNG が両方に無い)")
for d, n, _, _ in rows:
    print(f"{d:6.2f}%  {n}")
H = int(W * rows[0][2].size[1] / rows[0][2].size[0]) if rows else 0
s = Image.new("RGB", (2 * (W + 6), len(rows) * (H + 28)), "white")
dr = ImageDraw.Draw(s)
for i, (d, n, x, y) in enumerate(rows):
    yy = i * (H + 28)
    dr.text((4, yy + 4), f"{n}  差 {d:.2f}%   左 {LA} / 右 {LB}", fill="black", font=f)
    s.paste(x.resize((W, H), Image.LANCZOS), (0, yy + 26))
    s.paste(y.resize((W, H), Image.LANCZOS), (W + 6, yy + 26))
s.save(OUT)
print("sheet:", OUT)
