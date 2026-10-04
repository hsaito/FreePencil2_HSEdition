"""町のデモの連番(透明背景 4K)を白に載せて 1080p の mp4 にする。

  python assemble_town.py --src out/town_far [--pair out/town] [--fps 24]

--pair を渡すと、左に pair(今のまま)、右に src(奥の扱い)を並べた
比較動画 compare.mp4 も作る。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--pair", default="")
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--labels", default="今のまま(強弱);奥ほど細く・少なく・薄く")
A = ap.parse_args()
SRC = Path(A.src).resolve()
W, H = 1920, 1080


def onwhite(p: Path) -> Image.Image:
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((W, H), Image.LANCZOS)


def font(size):
    for p in (r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msgothic.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def encode(seq: Path, pattern: str, out: Path):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-framerate", str(A.fps), "-i", str(seq / pattern),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)],
                   check=True, capture_output=True)


def main():
    frames = sorted((SRC / "seq").glob("f????.png"))
    flat = SRC / "flat"
    if flat.exists():
        shutil.rmtree(flat)
    flat.mkdir()
    for i, p in enumerate(frames):
        onwhite(p).save(flat / f"f{i:05d}.png")
    encode(flat, "f%05d.png", SRC / "town_demo.mp4")
    print(f"{len(frames)}フレーム  {SRC / 'town_demo.mp4'}")
    # 6枚のシート
    pick = [frames[int(i * (len(frames) - 1) / 5)] for i in range(6)]
    sheet = Image.new("RGB", (3 * 646, 2 * 366), (120, 120, 120))
    for i, p in enumerate(pick):
        sheet.paste(onwhite(p).resize((640, 360), Image.LANCZOS),
                    (3 + (i % 3) * 646, 3 + (i // 3) * 366))
    sheet.save(SRC / "frames.png")
    if A.pair:
        other = sorted((Path(A.pair).resolve() / "seq").glob("f????.png"))
        n = min(len(frames), len(other))
        cmp_dir = SRC / "compare"
        if cmp_dir.exists():
            shutil.rmtree(cmp_dir)
        cmp_dir.mkdir()
        la, lb = A.labels.split(";")
        f = font(34)
        for i in range(n):
            fr = Image.new("RGB", (W * 2, H), (255, 255, 255))
            fr.paste(onwhite(other[i]), (0, 0))
            fr.paste(onwhite(frames[i]), (W, 0))
            d = ImageDraw.Draw(fr)
            d.line([(W, 0), (W, H)], fill=(150, 150, 158), width=3)
            d.text((40, 30), la, font=f, fill=(24, 24, 28))
            d.text((W + 40, 30), lb, font=f, fill=(24, 24, 28))
            fr.save(cmp_dir / f"f{i:05d}.png")
        encode(cmp_dir, "f%05d.png", SRC / "compare.mp4")
        print(f"{n}フレーム  {SRC / 'compare.mp4'}")


if __name__ == "__main__":
    main()
