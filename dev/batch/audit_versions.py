"""audit_panel.py を 2 つの版で回した結果を、同じ項目どうし並べて比べる。

5.2 だけ輪郭が二重になっていた(SetAlpha の設定が 5.x で書けていなかった)のは、
版をまたいで同じ絵を並べて初めて見えた。差の大きい順に並べて目で見る。

  python audit_versions.py out/audit/f452 out/audit/f520
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

A, B = (Path(p).resolve() for p in sys.argv[1:3])
ra = {(r["style"], r["prop"]): r for r in json.loads((A / "props.json").read_text(encoding="utf-8"))}
rb = {(r["style"], r["prop"]): r for r in json.loads((B / "props.json").read_text(encoding="utf-8"))}


def gray(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("L")


def diff(fa, fb):
    x, y = gray(A / fa), gray(B / fb)
    if x.size != y.size:
        y = y.resize(x.size)
    return float((np.abs(np.asarray(x, np.float32) - np.asarray(y, np.float32)) > 24).mean() * 100)


rows = []
done_a = set()
for key in sorted(set(ra) & set(rb)):
    style = key[0]
    if style not in done_a and ra[key].get("A") and rb[key].get("A"):      # 仕上がりごとの素の絵
        done_a.add(style)
        rows.append((diff(ra[key]["A"], rb[key]["A"]), (style, "(STEP0 そのまま)"), "A",
                     A / ra[key]["A"], B / rb[key]["A"]))
    if ra[key].get("C") and rb[key].get("C"):                              # 項目を変えた後
        rows.append((diff(ra[key]["C"], rb[key]["C"]), key, "C", A / ra[key]["C"], B / rb[key]["C"]))
rows.sort(key=lambda r: -r[0])
for d, key, img, _, _ in rows[:25]:
    print(f"{d:6.2f}%  {key[0]:10s} {key[1]:28s} {img}")
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 14)
top = rows[:10]
W, H = 320, 240
s = Image.new("RGB", (240 + 2 * (W + 4), len(top) * (H + 6)), "white")
d = ImageDraw.Draw(s)
for i, (dd, key, img, pa, pb) in enumerate(top):
    y = i * (H + 6)
    d.multiline_text((4, y + 6), f"{key[0]}\n{key[1]}\n({img})\n差 {dd:.2f}%\n左 {A.name} / 右 {B.name}", fill="black", font=f)
    for c, p in enumerate((pa, pb)):
        s.paste(gray(p).convert("RGB").resize((W, H)), (240 + c * (W + 4), y))
s.save(B / f"versus_{A.name}.png")
print("sheet:", B / f"versus_{A.name}.png")
