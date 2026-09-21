"""タイトル(FreePencil2 v2.8)+ 町の 30 秒 + BGM を 1 本の mp4 にする。

  python assemble_demo_movie.py --src out/town_v2/shot --bgm <mp3> --out out/town_v2/FreePencil2_v2.8_demo.mp4
      [--w 1920] [--title-sec 3.0] [--xfade 0.6]

タイトルは白地に濃い灰色の文字(線画に合わせる)。フェードイン -> 保持 ->
町の 1 フレーム目とクロスフェード。BGM は動画の長さで切り、最後 2 秒で
フェードアウト。
"""
import argparse, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True); ap.add_argument("--bgm", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--w", type=int, default=1920); ap.add_argument("--title-sec", type=float, default=3.0)
ap.add_argument("--xfade", type=float, default=0.6); ap.add_argument("--fps", type=int, default=24)
a = ap.parse_args()
W, H = a.w, a.w * 9 // 16
src = Path(a.src); work = src.parent / "demo_frames"
if work.exists(): shutil.rmtree(work)
work.mkdir()


def onwhite(p):
    im = Image.open(p).convert("RGBA"); bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im)
    return bg.convert("RGB").resize((W, H), Image.LANCZOS)


def font(name, size):
    for p in (rf"C:\Windows\Fonts\{name}",):
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    return ImageFont.load_default()


# タイトルカード(文字は 1 回描いて、明るさでフェード)
card = Image.new("RGB", (W, H), (255, 255, 255)); d = ImageDraw.Draw(card)
f1 = font("georgia.ttf", int(H * 0.13)); f2 = font("YuGothL.ttc", int(H * 0.036))
t1 = "FreePencil2"; t2 = "v2.8"; t3 = "Blender 用 線画アドオン  ―  手描き背景モード"
w1 = d.textlength(t1, font=f1); w2 = d.textlength(t2, font=font("georgia.ttf", int(H * 0.07)))
x0 = (W - (w1 + 30 + w2)) / 2; y0 = H * 0.40
d.text((x0, y0 - int(H * 0.13) * 0.55), t1, font=f1, fill=(40, 40, 44))
d.text((x0 + w1 + 30, y0 - int(H * 0.07) * 0.2), t2, font=font("georgia.ttf", int(H * 0.07)), fill=(90, 90, 96))
d.line([(W * 0.36, H * 0.50), (W * 0.64, H * 0.50)], fill=(120, 120, 126), width=2)
w3 = d.textlength(t3, font=f2); d.text(((W - w3) / 2, H * 0.53), t3, font=f2, fill=(90, 90, 96))

files = sorted(src.glob("f*.png"))
first = onwhite(files[0])
n_title = int(a.title_sec * a.fps); n_x = int(a.xfade * a.fps); n_in = int(0.8 * a.fps)
idx = 0
white = Image.new("RGB", (W, H), (255, 255, 255))
for k in range(n_title):
    t = min(1.0, k / max(1, n_in))                          # フェードイン
    Image.blend(white, card, t).save(work / f"f{idx:05d}.png"); idx += 1
for k in range(n_x):
    Image.blend(card, first, (k + 1) / n_x).save(work / f"f{idx:05d}.png"); idx += 1
for p in files:
    onwhite(p).save(work / f"f{idx:05d}.png"); idx += 1
total = idx / a.fps
ff = imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ff, "-y", "-framerate", str(a.fps), "-i", str(work / "f%05d.png"), "-i", a.bgm,
                "-filter_complex", f"[1:a]atrim=0:{total:.3f},afade=t=in:st=0:d=1.5,afade=t=out:st={total - 2.5:.3f}:d=2.5[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", "-shortest", a.out], check=True, capture_output=True)
card.save(src.parent / "title_card.png")
print(f"{idx} frames ({total:.1f}s) -> {a.out}")
