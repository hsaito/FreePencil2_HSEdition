"""連番のちらつきを、複数の版で並べて見る(v2.9 の「動くと遠景がちらつく」の測り台)。

  python flicker_compare.py --dirs out/v29/avenue/seq_cur,out/v29/avenue/seq_off --labels 今,OFF
      [--frames 50-73] [--crop 780,560,1140,760] [--out out/v29/avenue/flicker]

出力(すべて 1080p に縮めてから。再生で見る大きさ):
  heat.png    コマ間の 2 階差分 |I[t-1] - 2I[t] + I[t+1]| の平均。黒いほどちらつく
              (なめらかな動きは小さく、出たり消えたりする模様は大きい)
  strip.png   拡大した場所の連続 4 コマ(上から版ごと)
  数値は並べる順の目安。判定は strip.png の絵で行う
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
DIRS = [Path(p) for p in arg("--dirs").split(",")]
LABELS = arg("--labels", ",".join(d.name for d in DIRS)).split(",")
a, b = (int(v) for v in arg("--frames", "50-73").split("-"))
FR = list(range(a, b + 1))
CROP = tuple(int(v) for v in arg("--crop", "780,560,1140,760").split(","))
OUT = Path(arg("--out", str(DIRS[0].parent / "flicker")))
OUT.mkdir(parents=True, exist_ok=True)
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 20)


def view(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((1920, 1080), Image.LANCZOS)


heats = []
strips = []
for d, lab in zip(DIRS, LABELS):
    ims = [view(d / f"f{k:04d}.png") for k in FR]
    g = [np.asarray(im.convert("L"), np.float32) for im in ims]
    acc = np.zeros_like(g[0])
    for k in range(1, len(g) - 1):
        acc += np.abs(g[k - 1] - 2 * g[k] + g[k + 1])
    acc /= max(1, len(g) - 2)
    region = acc[CROP[1]:CROP[3], CROP[0]:CROP[2]]
    print(f"{lab}: 画面全体 {acc.mean():.2f} / 拡大の場所 {region.mean():.2f}")
    heats.append((lab, acc))
    strips.append((lab, [ims[k].crop(CROP) for k in range(len(ims) // 2, len(ims) // 2 + 4)]))

# heat
hw, hh = 960, 540
S = Image.new("RGB", (len(heats) * (hw + 6), hh + 30), "white")
d_ = ImageDraw.Draw(S)
for j, (lab, acc) in enumerate(heats):
    img = 255 - np.clip(acc * 3.0, 0, 255).astype(np.uint8)
    S.paste(Image.fromarray(img).convert("RGB").resize((hw, hh), Image.BOX), (j * (hw + 6), 28))
    d_.text((j * (hw + 6) + 6, 2), f"{lab}  ちらつき(黒いほど)", fill="black", font=f)
    x0, y0 = j * (hw + 6) + CROP[0] // 2, 28 + CROP[1] // 2
    d_.rectangle((x0, y0, x0 + (CROP[2] - CROP[0]) // 2, y0 + (CROP[3] - CROP[1]) // 2), outline=(230, 60, 0), width=2)
S.save(OUT / "heat.png")
# strip
Z = 2
cw, ch = (CROP[2] - CROP[0]) * Z, (CROP[3] - CROP[1]) * Z
T = Image.new("RGB", (4 * (cw + 4), len(strips) * (ch + 26)), "white")
d_ = ImageDraw.Draw(T)
for r, (lab, cs) in enumerate(strips):
    for c, im in enumerate(cs):
        T.paste(im.resize((cw, ch), Image.NEAREST), (c * (cw + 4), r * (ch + 26) + 24))
    d_.text((4, r * (ch + 26) + 2), f"{lab}  連続 4 コマ(1080p を 2 倍)", fill="black", font=f)
T.save(OUT / "strip.png")
print("saved", OUT)
