"""峡谷のカメラ移動を、つぶれ(左)と軽減(右)で並べた動画にする。
あわせて、コマ間の差の平均(白いほどちらつく)を画像にする。

  python assemble_canyon_move.py [--dir out/canyon_dense/move] [--out out/canyon_dense/canyon_move.mp4] [--fps 24]
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
HERE = Path(__file__).resolve().parent
D = Path(arg("--dir", str(HERE / "out" / "canyon_dense" / "move")))
OUT = Path(arg("--out", str(D.parent / "canyon_move.mp4")))
FPS = int(arg("--fps", "24"))
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 26)


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


names = sorted(p.name for p in (D / "r1").glob("f*.png"))
tmp = Path(tempfile.mkdtemp(prefix="canyon_move_"))
prev = {"r0": None, "r1": None}
acc = {"r0": None, "r1": None}
for k, n in enumerate(names):
    ims = {t: white(D / t / n) for t in ("r0", "r1")}
    w, h = ims["r0"].size
    for t, im in ims.items():
        g = np.asarray(im.convert("L"), np.float32)
        if prev[t] is not None:
            diff = np.abs(g - prev[t])
            acc[t] = diff if acc[t] is None else acc[t] + diff
        prev[t] = g
    S = Image.new("RGB", (2 * w + 6, h + 40), "white")
    d = ImageDraw.Draw(S)
    S.paste(ims["r0"], (0, 40))
    S.paste(ims["r1"], (w + 6, 40))
    d.text((10, 6), "つぶれ軽減 OFF", fill="black", font=f)
    d.text((w + 16, 6), "つぶれ軽減 ON(既定)", fill="black", font=f)
    S.save(tmp / f"c{k:04d}.png")
ff = imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ff, "-y", "-framerate", str(FPS), "-i", str(tmp / "c%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(OUT)], check=True)
print("video:", OUT, len(names), "frames")
# ちらつき地図(コマ間の差の平均。白いほど毎コマ変わる)
m = max(float(acc["r0"].max()), float(acc["r1"].max()), 1.0)
mean = {t: float(acc[t].mean() / (len(names) - 1)) for t in acc}
Fm = Image.new("RGB", (2 * w + 6, h + 40), "white")
d = ImageDraw.Draw(Fm)
for j, t in enumerate(("r0", "r1")):
    a = 255 - np.clip(acc[t] / (len(names) - 1) * 6.0, 0, 255).astype(np.uint8)
    Fm.paste(Image.fromarray(a).convert("RGB"), (j * (w + 6), 40))
    d.text((j * (w + 6) + 10, 6), f"{'OFF' if t == 'r0' else 'ON'}  コマ間の差の平均 {mean[t]:.2f}(黒いほど変わる)", fill="black", font=f)
Fm.save(OUT.with_name("canyon_move_flicker.png"))
print("flicker map saved; mean diff", mean)
