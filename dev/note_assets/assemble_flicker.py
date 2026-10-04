"""ちらつき比較: 短い試験クリップを 2 行 x 3 列に並べ、半分の速さで2回ループする。
あわせて、コマ間の差の平均を画像(白いほどちらつく)にして並べる(補助)。

  python assemble_flicker.py --tags a,b,c,d,e,f --labels "..." [--out out/grazing/flicker.mp4]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
D = Path(__file__).resolve().parent / "out" / "grazing"
TAGS = arg("--tags").split(",")
LB = arg("--labels", ",".join(TAGS)).split(",")
OUT = Path(arg("--out", str(D / "flicker.mp4")))
W, H = 640, 360
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 20)


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


names = sorted(p.name for p in (D / f"movie_{TAGS[0]}").glob("f*.png"))
cols = 3
rows = (len(TAGS) + cols - 1) // cols
tmp = Path(tempfile.mkdtemp(prefix="flicker_"))
k = 0
diffs = {t: None for t in TAGS}
prev = {t: None for t in TAGS}
for loop in range(2):
    for n in names:
        s = Image.new("RGB", (cols * (W + 6), rows * (H + 34)), "white")
        d = ImageDraw.Draw(s)
        for i, (t, lb) in enumerate(zip(TAGS, LB)):
            im = white(D / f"movie_{t}" / n).resize((W, H), Image.LANCZOS)
            x, y = (i % cols) * (W + 6), (i // cols) * (H + 34)
            s.paste(im, (x, y + 30))
            d.text((x + 6, y + 4), lb, fill="black", font=f)
            if loop == 0:
                a = np.asarray(im.convert("L"), dtype=np.float32)
                if prev[t] is not None:
                    dd = np.abs(a - prev[t])
                    diffs[t] = dd if diffs[t] is None else diffs[t] + dd
                prev[t] = a
        for _ in range(2):                      # 半分の速さ
            s.save(tmp / f"{k:05d}.png")
            k += 1
ff = imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", "24", "-i", str(tmp / "%05d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(OUT)], check=True)
# ちらつきの地図(カメラが動く分も含むので、比べるのは案どうしの差)
s = Image.new("RGB", (cols * (W + 6), rows * (H + 34)), "white")
d = ImageDraw.Draw(s)
for i, (t, lb) in enumerate(zip(TAGS, LB)):
    m = diffs[t] / (len(names) - 1)
    x, y = (i % cols) * (W + 6), (i // cols) * (H + 34)
    s.paste(Image.fromarray(np.clip(m * 4, 0, 255).astype(np.uint8)).convert("RGB"), (x, y + 30))
    d.text((x + 6, y + 4), f"{lb}  平均 {m.mean():.2f}", fill="black", font=f)
s.save(OUT.with_suffix(".png"))
print(OUT)
