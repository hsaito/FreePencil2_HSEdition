"""カメラを下ろす試験動画(案ごと)を横に並べ、ラベルを付けて1本にする。

  python assemble_grazing.py --variants cur,cr_r8c45,cr_r12c45 --labels "今,新案A,新案B" [--out out/grazing/compare.mp4]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
D = HERE / "out" / "grazing"
VS = arg("--variants").split(",")
LB = arg("--labels", ",".join(VS)).split(",")
OUT = Path(arg("--out", str(D / "compare.mp4")))
W = int(arg("--w", "640"))
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 22)


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


frames = sorted((D / f"movie_{VS[0]}").glob("f*.png"))
tmp = Path(tempfile.mkdtemp(prefix="grazing_"))
H = W * 9 // 16
for i, p in enumerate(frames):
    s = Image.new("RGB", (len(VS) * (W + 6) - 6, H + 36), "white")
    d = ImageDraw.Draw(s)
    for j, (v, lb) in enumerate(zip(VS, LB)):
        im = white(D / f"movie_{v}" / p.name).resize((W, H), Image.LANCZOS)
        s.paste(im, (j * (W + 6), 36))
        d.text((j * (W + 6) + 8, 6), lb, fill="black", font=f)
    s.save(tmp / f"{i:04d}.png")
ff = imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", "24", "-i", str(tmp / "%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(OUT)], check=True)
print(f"{len(frames)} frames -> {OUT}")
