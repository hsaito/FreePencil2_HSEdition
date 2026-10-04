"""test_char_motion.py の結果を、線画とボーンの塗りを左右に並べた動画にする。

  python assemble_char_motion.py [--dir out/char_motion] [--out out/char_motion/char_motion.mp4]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ARGV = sys.argv[1:]


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


D = Path(arg("--dir", str(HERE / "out" / "char_motion")))
OUT = Path(arg("--out", str(D / "char_motion.mp4")))
FONT = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 22)
W, H = 960, 540


def main():
    frames = sorted((D / "line").glob("f*.png"))
    tmp = Path(tempfile.mkdtemp(prefix="char_motion_"))
    for i, p in enumerate(frames):
        a = Image.open(p).convert("RGBA")
        bg = Image.new("RGBA", a.size, (255, 255, 255, 255))
        bg.alpha_composite(a)
        a = bg.convert("RGB").resize((W, H), Image.LANCZOS)
        b = Image.open(D / "bone" / p.name).convert("RGB").resize((W, H), Image.LANCZOS)
        s = Image.new("RGB", (W * 2, H), "white")
        s.paste(a, (0, 0))
        s.paste(b, (W, 0))
        d = ImageDraw.Draw(s)
        d.text((12, 8), "キャラ(手描き)の線画", fill=(0, 0, 0), font=FONT)
        d.text((W + 12, 8), "ボーンの塗り bone_color(境目はウェイトでぼかし)",
               fill=(255, 255, 255), font=FONT)
        s.save(tmp / f"{i:04d}.png")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", "24",
                    "-i", str(tmp / "%04d.png"), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "18", str(OUT)], check=True)
    print(f"{len(frames)} frames -> {OUT}")


if __name__ == "__main__":
    main()
