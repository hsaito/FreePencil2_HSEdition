"""60 秒デモ: 背景・メカ・キャラを見せて、最後に3つを並べる。曲は「最終決戦の序曲」。

  python assemble_demo60.py --song <mp3> [--preview] [--out out/demo60/FreePencil2_v2.8_demo60.mp4]

区切りは曲の音の引き(5 / 10.3 / 36 / 56 秒)と山(49〜52 秒)に合わせ、近くの
一番強い拍へ 0.3 秒以内で吸い付ける。素材:
  町(線)      out/town_v4/shot_final/f####.png   (撮影済みの最高品質)
  町(3D だけ) out/demo60/town_plain[_preview]/f####.png   (冒頭のワイプ)
  メカ         out/demo60/kuka[_preview]/f####.png
  キャラ       out/demo60/char[_preview]/line/f####.png
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
O = HERE / "out"
PREV = "--preview" in ARGV
W = 960 if PREV else 1920
H = W * 9 // 16
FPS = 24
SONG = Path(arg("--song") or sys.exit("--song <曲の mp3> を指定してください"))
OUT = Path(arg("--out", str(O / "demo60" / ("demo60_preview.mp4" if PREV else "FreePencil2_v2.8_demo60.mp4"))))
sfx = "_preview" if PREV else ""
SRC = {
    "town": O / "town_v4" / "shot_final",
    "plain": O / "demo60" / f"town_vcol{sfx}",      # 塗り分け(mecha_color)の素通し
    "kuka": O / "demo60" / f"kuka{sfx}",
    "char": O / "demo60" / f"char{sfx}" / "line",
}
S = W / 1920                                    # 文字の大きさの倍率
F_BIG = ImageFont.truetype("C:/Windows/Fonts/YuGothB.ttc", int(96 * S))
F_MID = ImageFont.truetype("C:/Windows/Fonts/YuGothB.ttc", int(44 * S))
F_SUB = ImageFont.truetype("C:/Windows/Fonts/YuGothM.ttc", int(30 * S))
F_SMALL = ImageFont.truetype("C:/Windows/Fonts/YuGothM.ttc", int(26 * S))
INK = (38, 38, 42)
GREY = (120, 120, 124)


# ---------------------------------------------------------------- 曲の拍

def onsets():
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    raw = subprocess.run([ff, "-loglevel", "error", "-i", str(SONG), "-ac", "1", "-ar", "22050",
                          "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    hop, n = 512, 1024
    m = len(x) // hop - 2
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft(np.stack([x[i * hop:i * hop + n] * win for i in range(m)]), axis=1))
    flux = np.r_[0, np.maximum(0, np.diff(np.log1p(spec), axis=0)).sum(1)]
    return np.arange(m) * hop / 22050, flux


def snap(t0, t, flux, reach=0.3):
    sel = (t > t0 - reach) & (t < t0 + reach)
    return float(t[sel][np.argmax(flux[sel])]) if sel.any() else t0


# ---------------------------------------------------------------- 絵

def load(kind, f):
    p = SRC[kind] / f"f{f:04d}.png"
    im = Image.open(p).convert("RGBA")
    if kind == "plain":
        # 塗らない地面(道路)は真っ黒に出る。線画と同じ明るい灰色にする
        a = np.asarray(im).copy()
        blk = (a[..., 3] > 200) & (a[..., :3].max(axis=2) < 6)
        a[blk, :3] = 214
        im = Image.fromarray(a)
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((W, H), Image.LANCZOS)


def frames_of(kind):
    return sorted(int(p.stem[1:]) for p in SRC[kind].glob("f*.png"))


def caption(im, title, sub, alpha=1.0):
    """左下に、白い帯の上へ見出しと説明。"""
    if alpha <= 0:
        return im
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    x, y = int(56 * S), H - int(170 * S)
    tw = max(d.textlength(title, font=F_MID), d.textlength(sub, font=F_SUB))
    d.rectangle([x - int(24 * S), y - int(18 * S), x + tw + int(28 * S), y + int(118 * S)],
                fill=(255, 255, 255, int(215 * alpha)))
    d.rectangle([x - int(24 * S), y - int(18 * S), x - int(16 * S), y + int(118 * S)],
                fill=INK + (int(255 * alpha),))
    d.text((x, y), title, font=F_MID, fill=INK + (int(255 * alpha),))
    d.text((x, y + int(62 * S)), sub, font=F_SUB, fill=GREY + (int(255 * alpha),))
    out = im.convert("RGBA")
    out.alpha_composite(ov)
    return out.convert("RGB")


def card(lines, sub=None):
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    big, small = lines
    bw = d.textlength(big, font=F_BIG)
    sw = d.textlength(small, font=F_MID)
    y = H // 2 - int(90 * S)
    d.text(((W - bw - sw - 20 * S) / 2, y), big, font=F_BIG, fill=INK)
    d.text(((W - bw - sw - 20 * S) / 2 + bw + 20 * S, y + int(40 * S)), small, font=F_MID, fill=GREY)
    d.line([(W / 2 - 260 * S, y + 140 * S), (W / 2 + 260 * S, y + 140 * S)], fill=(190, 190, 194), width=max(1, int(2 * S)))
    if sub:
        uw = d.textlength(sub, font=F_SUB)
        d.text(((W - uw) / 2, y + 162 * S), sub, font=F_SUB, fill=GREY)
    return im


def fade(a, b, k):
    return Image.blend(a, b, max(0.0, min(1.0, k)))


def main():
    t, flux = onsets()
    plan = [4.8, 10.4, 24.0, 36.0, 48.0, 56.0]
    cuts = [0.0] + [snap(c, t, flux) for c in plan] + [60.0]
    fr = [int(round(c * FPS)) for c in cuts]
    print("cuts(s):", [round(c, 2) for c in cuts])
    n_total = fr[-1]
    town, kuka, char = frames_of("town"), frames_of("kuka"), frames_of("char")
    title = card(("FreePencil2", "v2.8"), "Blender 用 線画アドオン")
    end = card(("FreePencil2", "v2.8"), "Blender 4.2 – 5.2 対応")
    tmp = Path(tempfile.mkdtemp(prefix="demo60_"))
    xf = int(0.5 * FPS)                          # タイトル -> 冒頭のクロスフェード
    town_i = 0                                   # 町の素材をどこまで使ったか

    def town_frame(i):
        return load("town", town[min(i, len(town) - 1)])

    for k in range(n_total):
        if k < fr[1]:                            # タイトル(最後 0.5 秒で冒頭へ)
            im = fade(Image.new("RGB", (W, H), "white"), title, k / (0.8 * FPS))
            if k >= fr[1] - xf:
                im = fade(im, load("plain", town[0]), (k - (fr[1] - xf)) / xf)
        elif k < fr[2]:                          # 3D -> 線画のワイプ
            j = k - fr[1]
            town_i = j
            line = town_frame(j)
            plain = load("plain", town[j]) if (SRC["plain"] / f"f{town[j]:04d}.png").exists() else line
            s = (j - 1.2 * FPS) / (2.6 * FPS)    # 1.2 秒 3D を見せてから 2.6 秒で払う
            s = 0.0 if s < 0 else (1.0 if s > 1 else 0.5 - 0.5 * np.cos(s * np.pi))
            cx = int(W * s)
            im = plain.copy()
            im.paste(line.crop((0, 0, cx, H)), (0, 0))
            if 0 < cx < W:
                ImageDraw.Draw(im).line([(cx, 0), (cx, H)], fill=INK, width=max(2, int(4 * S)))
            a = min(1.0, (j - 3.9 * FPS) / (0.4 * FPS)) if j > 3.9 * FPS else 0.0
            im = caption(im, "ボタン1つで、3D を線画に", "塗り分けた色の境目を、線にする", a)
        elif k < fr[3]:                          # 背景
            j = k - fr[2]
            im = town_frame(town_i + 1 + j)
            a = min(1.0, j / (0.4 * FPS))
            im = caption(im, "背景 ─ 手描き背景", "遠くも細部も、つぶさず描き分ける", a)
        elif k < fr[4]:                          # メカ
            j = k - fr[3]
            im = load("kuka", kuka[min(j, len(kuka) - 1)])
            im = caption(im, "メカ ─ 精密", "パネルの線を、全部拾う", min(1.0, j / (0.4 * FPS)))
        elif k < fr[5]:                          # キャラ
            j = k - fr[4]
            im = load("char", char[min(j, len(char) - 1)])
            im = caption(im, "キャラ ─ キャラ(手描き)", "ほんのり強弱。関節で線が切れない", min(1.0, j / (0.4 * FPS)))
        elif k < fr[6]:                          # 3つを並べる
            j = k - fr[5]
            # 画面を縦に3つに割って並べる(それぞれ主役が真ん中に来るように切り出す)
            im = Image.new("RGB", (W, H), "white")
            d = ImageDraw.Draw(im)
            sw = W // 3
            n_town = len(town)
            srcs = [(town_frame(n_town - (fr[6] - fr[5]) + j), 0.5, "背景", "手描き背景"),
                    (load("kuka", kuka[min(8 + j, len(kuka) - 1)]), 0.62, "メカ", "精密"),
                    (load("char", char[min(j, len(char) - 1)]), 0.5, "キャラ", "キャラ(手描き)")]
            for i, (src, cxr, lb, style) in enumerate(srcs):
                x0 = int(min(max(W * cxr - sw / 2, 0), W - sw))
                im.paste(src.crop((x0, 0, x0 + sw, H)), (i * sw, 0))
                if i:
                    d.line([(i * sw, 0), (i * sw, H)], fill=INK, width=max(2, int(4 * S)))
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            head = "モデルに合わせて、塗り方を自動で切り替え"
            hw = od.textlength(head, font=F_MID)
            od.rectangle([(W - hw) / 2 - 30 * S, 36 * S, (W + hw) / 2 + 30 * S, 116 * S], fill=(255, 255, 255, 225))
            od.text(((W - hw) / 2, 48 * S), head, font=F_MID, fill=INK)
            for i, (_, _, lb, style) in enumerate(srcs):
                txt = f"{lb}  /  {style}"
                tw = od.textlength(txt, font=F_SUB)
                cx = i * sw + sw / 2
                od.rectangle([cx - tw / 2 - 20 * S, H - 96 * S, cx + tw / 2 + 20 * S, H - 40 * S], fill=(255, 255, 255, 225))
                od.text((cx - tw / 2, H - 88 * S), txt, font=F_SUB, fill=INK)
            im = im.convert("RGBA")
            im.alpha_composite(ov)
            im = im.convert("RGB")
            a = min(1.0, j / (0.5 * FPS))
            if a < 1.0:
                im = fade(load("char", char[min(fr[5] - fr[4] - 1, len(char) - 1)]), im, a)
        else:                                    # 締め
            j = k - fr[6]
            im = fade(im_last, end, j / (0.6 * FPS)) if j < 0.6 * FPS else end
            tail = n_total - k
            if tail < 0.8 * FPS:
                im = fade(Image.new("RGB", (W, H), "white"), im, tail / (0.8 * FPS))
        if k == fr[6] - 1:
            im_last = im
        im.save(tmp / f"{k:05d}.png")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "%05d.png"),
                    "-i", str(SONG), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "16" if not PREV else "22", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{n_total / FPS:.3f}", "-af", "afade=t=out:st=58.8:d=1.2", str(OUT)], check=True)
    print(OUT)


if __name__ == "__main__":
    main()
