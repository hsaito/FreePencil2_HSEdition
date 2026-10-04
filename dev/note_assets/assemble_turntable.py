"""eval_lw_movie.py が撮った 精密(off)/強弱(on) の回転を左右に並べて mp4 にする。

つぶれの確認用。縮小せず、フルHD 2枚を横に並べる(3840x1080)。
文字は上に小さく置くだけで、絵には手を入れない。

  python dev/note_assets/assemble_turntable.py --src out/tt_camera [--fps 24]
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
W, H = 1920, 1080


def _mod(name, path):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")


def onwhite(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--label", default="")
    # 強弱側だけを 1920x1080 の単独動画にもする(全画面で見るため)
    ap.add_argument("--solo", action="store_true")
    a = ap.parse_args()
    src = Path(a.src)
    offs = sorted((src / "off").glob("f*.png"))
    ons = sorted((src / "on").glob("f*.png"))
    n = min(len(offs), len(ons))
    if n == 0:
        raise SystemExit(f"素材が無い: {src}")
    seq = src / "seq"
    if seq.exists():
        shutil.rmtree(seq)
    seq.mkdir()
    f = mx.font(34)
    for i in range(n):
        fr = Image.new("RGB", (W * 2, H), (255, 255, 255))
        fr.paste(onwhite(offs[i]), (0, 0))
        fr.paste(onwhite(ons[i]), (W, 0))
        d = ImageDraw.Draw(fr)
        d.line([(W, 0), (W, H)], fill=(150, 150, 158), width=3)
        d.text((40, 30), f"精密(v2.7)  {a.label}", font=f, fill=(24, 24, 28))
        d.text((W + 40, 30), f"強弱(手描き)  {a.label}", font=f, fill=(24, 24, 28))
        fr.save(seq / f"f{i:05d}.png")
    out = src / "turntable.mp4"
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-framerate", str(a.fps),
           "-i", str(seq / "f%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "18", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"{n}フレーム  {out}")
    if a.solo:
        solo = src / "solo"
        if solo.exists():
            shutil.rmtree(solo)
        solo.mkdir()
        for i in range(n):
            onwhite(ons[i]).save(solo / f"f{i:05d}.png")
        out2 = src / "weighted_1080p.mp4"
        subprocess.run([ff, "-y", "-framerate", str(a.fps),
                        "-i", str(solo / "f%05d.png"), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "18", str(out2)],
                       check=True, capture_output=True)
        print(f"{n}フレーム  {out2}")


if __name__ == "__main__":
    main()
