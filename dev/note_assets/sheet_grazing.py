"""試験場の静止画を案ごとに並べる(高さ 1.5m の奥を拡大)。

  python sheet_grazing.py --variants cur,off,... [--height 1.5] [--out name.png]
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
D = Path(__file__).resolve().parent / "out" / "grazing" / "stills"
VS = arg("--variants").split(",")
H = arg("--height", "1.5")
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 20)


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


cells = []
for v in VS:
    im = white(D / f"{v}_h{H}.png")
    w, h = im.size
    c = im.crop((int(w * 0.52), int(h * 0.15), int(w * 0.8), int(h * 0.7)))
    c = c.resize((480, int(480 * c.height / c.width)), Image.LANCZOS)
    cells.append((v, c))
cols = 5
ch = cells[0][1].height
rows = (len(cells) + cols - 1) // cols
s = Image.new("RGB", (cols * 490 + 10, rows * (ch + 34) + 10), "white")
d = ImageDraw.Draw(s)
for i, (v, c) in enumerate(cells):
    x, y = 10 + (i % cols) * 490, 10 + (i // cols) * (ch + 34)
    d.text((x, y), v, fill="black", font=f)
    s.paste(c, (x, y + 28))
out = D / arg("--out", f"sheet_h{H}.png")
s.save(out)
print(out)
