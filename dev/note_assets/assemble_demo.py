"""撮った連番を30秒のデモに組み立てる。

make_demo_movie.py が撮ったショットを並べ、ワイプ・画面分割・タイトルを
合成して1本の連番にする。動画化は fp_batch.encode_video に渡す。

  0.0- 6.0s  hero    線なし -> 縦ワイプ -> 線あり。同じ物だと分かるように
  6.0-18.0s  montage 5体。切り替えは短いクロスフェード
 18.0-23.0s  split   左に塗り分け、右に線。仕組みがそのまま見える
 23.0-30.0s  title   文字だけ

Blender は動画化にしか使わないので、合成は Pillow で行う。

    python dev/note_assets/assemble_demo.py --src demo_hd [--fps 24]

--src は out/ の下の名前でも、パスそのものでもよい。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
BLENDER = r"C:\blender\blender-4.5.2-windows-x64\blender.exe"

# 記事と揃えた見出し。数字は実測値のみ
TITLE_LINES = [
    ("FreePencil2", 78),
    ("Blender のトゥーン線画アドオン", 34),
]
SUB_LINES = [
    "STEP0 を1回押すだけ",
    "42万ポリゴンの戦車で約19秒",
    "note.com/megamarsun",
]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
    r"C:\Windows\Fonts\segoeui.ttf",
]


def font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def load(path, size):
    im = Image.open(path).convert("RGB")
    return im if im.size == size else im.resize(size, Image.LANCZOS)


def frames_of(d):
    return sorted(Path(d).glob("f*.png"))


def wipe(a, b, t, feather=90):
    """左から右へ縦のワイプ。境目に細い線を置いて、切り替えを見せる。"""
    w, h = a.size
    x = int(w * t)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rectangle([0, 0, x, h], fill=255)
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather / 6))
    out = Image.composite(b, a, mask)
    if 0 < x < w:
        ImageDraw.Draw(out).line([(x, 0), (x, h)], fill=(255, 255, 255),
                                 width=max(3, int(3 * w / 1280.0)))
    return out


def crossfade(a, b, t):
    return Image.blend(a, b, t)


def label(im, text, sub=None, alpha=1.0):
    """左下に小さく置く見出し。絵の邪魔をしない大きさに留める。"""
    if alpha <= 0.0:
        return im
    w, h = im.size
    k = w / 1280.0          # 1280 基準で組んだ値を解像度に追従させる
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f1, f2 = font(int(38 * k)), font(int(24 * k))
    x, y = int(62 * k), h - int(132 * k)
    d.text((x, y), text, font=f1, fill=(20, 20, 22, int(255 * alpha)))
    if sub:
        d.text((x, y + int(52 * k)), sub, font=f2,
               fill=(20, 20, 22, int(200 * alpha)))
    return Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")


def title_frame(size, t):
    """最後のタイトル。t は 0..1 で、文字が順に出る。"""
    w, h = size
    k = w / 1280.0
    im = Image.new("RGB", size, (244, 244, 242))
    d = ImageDraw.Draw(im)
    y = int(h * 0.30)
    for i, (text, sz) in enumerate(TITLE_LINES):
        a = max(0.0, min(1.0, (t - i * 0.10) / 0.28))
        if a <= 0:
            continue
        f = font(int(sz * k))
        tw = d.textlength(text, font=f)
        g = int(30 * k * (1 - a))
        v = int(26 + (1 - a) * 180)
        d.text(((w - tw) / 2, y + g), text, font=f, fill=(v, v, v + 2))
        y += int(sz * k * 1.5)
    y += int(26 * k)
    for i, text in enumerate(SUB_LINES):
        a = max(0.0, min(1.0, (t - 0.34 - i * 0.09) / 0.26))
        if a <= 0:
            continue
        f = font(int(26 * k))
        tw = d.textlength(text, font=f)
        v = int(90 + (1 - a) * 150)
        d.text(((w - tw) / 2, y), text, font=f, fill=(v, v, v))
        y += int(44 * k)
    return im


def build(src: Path, out: Path, fps: int):
    meta = json.loads((src / "shots.json").read_text("utf-8"))
    W, H = meta["res"]
    size = (W, H)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    n = 0

    def put(im):
        nonlocal n
        im.save(out / f"d{n:05d}.png")
        n += 1

    # --- hero: 線なし -> ワイプ -> 線あり ---
    plain = frames_of(src / "tank_plain")
    line = frames_of(src / "tank_line")
    if plain and line:
        total = min(len(plain), len(line))
        w0, w1 = int(total * 0.34), int(total * 0.60)
        for i in range(total):
            a = load(plain[i], size)
            b = load(line[i], size)
            if i < w0:
                im, txt, sub = a, "3Dモデル", "線は入っていません"
            elif i < w1:
                t = (i - w0) / max(w1 - w0, 1)
                im = wipe(a, b, t)
                txt, sub = "STEP0 を押す", None
            else:
                im, txt, sub = b, "線画", "ボタン1回・手作業なし"
            put(label(im, txt, sub))

    # --- montage: 5体をクロスフェードでつなぐ ---
    seqs = [frames_of(src / f"{r['tag']}_line") for r in meta["rows"]
            if r["tag"] not in ("tank", "camera") and "line" in r["modes"]]
    seqs = [s for s in seqs if s]
    fade = 6
    for k, seq in enumerate(seqs):
        for i, f in enumerate(seq):
            im = load(f, size)
            if k > 0 and i < fade:
                prev = load(seqs[k - 1][-1], size)
                im = crossfade(prev, im, (i + 1) / (fade + 1))
            put(label(im, "同じ設定のまま", "モデルを変えるだけ",
                      alpha=1.0 if k == 0 else 0.0))

    # --- split: 左に塗り分け、右に線 ---
    paint = frames_of(src / "camera_paint")
    cline = frames_of(src / "camera_line")
    if paint and cline:
        half = W // 2
        for i in range(min(len(paint), len(cline))):
            p = load(paint[i], size).crop((half // 2, 0, half // 2 + half, H))
            c = load(cline[i], size).crop((half // 2, 0, half // 2 + half, H))
            im = Image.new("RGB", size, (255, 255, 255))
            im.paste(p, (0, 0))
            im.paste(c, (half, 0))
            ImageDraw.Draw(im).line([(half, 0), (half, H)],
                                    fill=(255, 255, 255),
                                    width=max(4, int(4 * W / 1280.0)))
            put(label(im, "色の境目が線になる",
                      "左：自動の塗り分け　右：出てくる線"))

    # --- title ---
    n_title = int(fps * 7.0)
    for i in range(n_title):
        put(title_frame(size, i / max(n_title - 1, 1)))

    return n, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="demo",
                    help="out/ の下の名前、またはパス")
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()

    src = Path(a.src)
    if not src.exists():
        # 名前だけ渡されたときは out/ の下を見る。リポジトリ直下から
        # 実行しても、note_assets の中から実行しても同じように通る
        src = HERE / "out" / a.src
    if not src.exists():
        raise SystemExit(f"見つからない: {a.src}")
    out = src / "assembled"
    n, size = build(src, out, a.fps)
    print(f"[demo] {n} frames ({n / a.fps:.1f}s) -> {out}")

    mp4 = src / "freepencil_demo.mp4"
    code = (
        "import sys, pathlib\n"
        f"sys.path.insert(0, r'{HERE.parent / 'batch'}')\n"
        "import fp_batch\n"
        f"paths = sorted(pathlib.Path(r'{out}').glob('d*.png'))\n"
        f"fp_batch.encode_video(paths, pathlib.Path(r'{mp4}'), {a.fps},"
        f" {size[0]}, {size[1]})\n"
    )
    tmp = src / "_encode.py"
    tmp.write_text(code, encoding="utf-8")
    # Blender は書き出しを終えたあと終了時に非ゼロで落ちることがある
    # (実測: mp4 は正しく出来ているのに exit 11)。終了コードではなく
    # 出来たファイルで成否を見る
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python",
                        str(tmp)], capture_output=True)
    tmp.unlink(missing_ok=True)
    if not mp4.exists() or mp4.stat().st_size < 10_000:
        raise SystemExit(
            f"動画が出来ていない (exit {r.returncode})\n"
            + r.stderr.decode("utf-8", "replace")[-600:])
    print(f"[demo] {mp4} ({mp4.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
