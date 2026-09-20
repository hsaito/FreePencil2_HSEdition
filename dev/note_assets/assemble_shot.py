"""shoot_town_v2.py の連番を白に載せて mp4 にする。

  python assemble_shot.py --src out/town_v2/shot [--w 1920] [--out out/town_v2/town_v2_30s.mp4]
"""
import argparse, shutil, subprocess
from pathlib import Path
from PIL import Image
import imageio_ffmpeg
ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True); ap.add_argument("--w", type=int, default=1920); ap.add_argument("--out", default="")
a = ap.parse_args()
src = Path(a.src); flat = src.parent / (src.name + "_flat")
if flat.exists(): shutil.rmtree(flat)
flat.mkdir()
files = sorted(src.glob("f*.png"))
W, H = a.w, a.w * 9 // 16
for i, p in enumerate(files):
    im = Image.open(p).convert("RGBA"); bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im)
    bg.convert("RGB").resize((W, H), Image.LANCZOS).save(flat / f"f{i:05d}.png")
out = Path(a.out) if a.out else src.parent / (src.name + ".mp4")
ff = imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ff, "-y", "-framerate", "24", "-i", str(flat / "f%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)], check=True, capture_output=True)
print(len(files), "frames ->", out)
