"""透過 PNG の連番を、白地に重ねた H.264 の動画にする(4K と 1080p の 2 本)。

  python assemble_plain_video.py --dir out/avenue/fly4k --out out/avenue/avenue_fly.mp4 [--fps 24]
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
D = Path(arg("--dir"))
OUT = Path(arg("--out", str(D.parent / "out.mp4")))
FPS = int(arg("--fps", "24"))


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


names = sorted(p.name for p in D.glob("f*.png"))
W, H = white(D / names[0]).size
ff = imageio_ffmpeg.get_ffmpeg_exe()
common = ["-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(FPS), "-i", "-"]
hd = OUT.with_name(OUT.stem + "_1080p.mp4")
p1 = subprocess.Popen([ff, *common, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "14", "-preset", "slow", str(OUT)],
                      stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
p2 = subprocess.Popen([ff, *common, "-vf", "scale=1920:1080:flags=lanczos", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                       "-crf", "16", "-preset", "slow", str(hd)],
                      stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for n in names:
    raw = np.asarray(white(D / n), dtype=np.uint8).tobytes()
    p1.stdin.write(raw)
    p2.stdin.write(raw)
for p in (p1, p2):
    p.stdin.close()
    p.wait()
print("video:", OUT, len(names), "frames", f"{W}x{H}")
print("1080p:", hd)
