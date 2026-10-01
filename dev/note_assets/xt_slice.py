"""連番の「時空間スライス」: 画面の 1 行を、コマごとに縦に積んで 1 枚にする。

  python xt_slice.py --dir out/canyon2/move70 --rows 0.45,0.75 [--scale 2] [--x0 0 --x1 1]

なめらかな動きは、斜めの筋がなめらかに流れる。ちらつき(時間方向のエイリアシング)は、
筋がちぎれる・向きが入れ替わる・細かい格子になる、という形で見える。
左が OFF、右が ON(同じ行・同じ範囲)。上から下へ時間が進む。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
D = Path(arg("--dir", "out/canyon2/move70"))
ROWS = [float(v) for v in arg("--rows", "0.45,0.75").split(",")]
SC = int(arg("--scale", "2"))
X0, X1 = float(arg("--x0", "0.0")), float(arg("--x1", "1.0"))
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 22)


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    g = bg.convert("L")
    if SC > 1:
        g = g.resize((g.size[0] // SC, g.size[1] // SC), Image.BOX)
    return np.asarray(g, np.uint8)


names = sorted(p.name for p in (D / "r1").glob("f*.png"))
slices = {t: {r: [] for r in ROWS} for t in ("r0", "r1")}
for n in names:
    for t in ("r0", "r1"):
        g = white(D / t / n)
        h, w = g.shape
        for r in ROWS:
            slices[t][r].append(g[int(h * r), int(w * X0):int(w * X1)])
for r in ROWS:
    a = np.stack(slices["r0"][r])
    b = np.stack(slices["r1"][r])
    H, W = a.shape
    S = Image.new("L", (2 * W + 8, H + 34), 255)
    d = ImageDraw.Draw(S)
    S.paste(Image.fromarray(a), (0, 34))
    S.paste(Image.fromarray(b), (W + 8, 34))
    d.text((4, 4), f"軽減 OFF  行 {r:.2f} の時間変化(上→下 = 1→{H} コマ)", fill=0, font=f)
    d.text((W + 12, 4), "軽減 ON", fill=0, font=f)
    out = D.parent / f"xt_{int(r * 100):02d}.png"
    S.save(out)
    print(out, S.size)
