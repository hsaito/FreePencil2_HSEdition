"""v2.7 の機能紹介デモを1本に組み立てる。

素材:
  out/v27/hero_line          メカの回転 (掴み)
  out/v27/sens_100 / _050    帆船の同じ回転を、感度 1.0 と 0.5 で
  out/v27_town_off/frames    町のドリー・遠景つぶれ軽減 OFF
  out/v27_town_on/frames     同 ON
  out/livecap/c*.jpg         実キャプチャ (進捗バーの実物)

構成 (24fps):
  0.0- 4.5s  hero    回しながら線画
  4.5-12.5s  sens    左右に並べて比較 -> 0.5 に寄る
 12.5-21.5s  town    ドリー。OFF から ON へワイプ
 21.5-26.5s  speed   実キャプチャ。155パーツの進捗バー
 26.5-30.5s  title

    python dev/note_assets/assemble_v27_movie.py [--fps 24]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
OUTROOT = HERE / "out"
DST = OUTROOT / "v27_final"
FRAMES = DST / "frames"
MP4 = DST / "freepencil_v27.mp4"
BLENDER = r"C:\blender\blender-4.5.2-windows-x64\blender.exe"

W, H = 1600, 900
TOWN_ON = "v27_town_on"
FONTS = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc",
         r"C:\Windows\Fonts\msgothic.ttc"]


def font(size: int):
    for p in FONTS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def seq(d: Path, pattern: str = "f*.png") -> list[Path]:
    return sorted(d.glob(pattern)) if d.exists() else []


def load(p: Path, on_white: bool = True) -> Image.Image:
    """素材を 16:9 の画面に収める。透過は白地に置く。

    町の素材は、アドオンの細線化(Scale 0.5)のせいで実画像が canvas の
    中央 50% にしか無い。周りは完全な透明。実測で x,y とも 0.25..0.75
    だった。透明な余白があるときは、中身だけを取り出す。
    """
    im = Image.open(p)
    if im.mode == "RGBA":
        box = im.getbbox()
        if box and (box[2] - box[0]) * (box[3] - box[1]) < im.width * im.height * 0.9:
            im = im.crop(box)
    if im.mode == "RGBA" and on_white:
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    im = im.convert("RGB")
    if im.size == (W, H):
        return im
    k = min(W / im.width, H / im.height)
    w, h = round(im.width * k), round(im.height * k)
    out = Image.new("RGB", (W, H), (255, 255, 255))
    out.paste(im.resize((w, h), Image.LANCZOS), ((W - w) // 2, (H - h) // 2))
    return out


def caption(im: Image.Image, main: str, sub: str | None = None,
            dark: bool = False) -> Image.Image:
    """下に帯を敷いて字幕。絵の上に直接置くと読めないことがある。"""
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 104, W, H], fill=(16, 16, 18) if not dark
                else (10, 10, 12))
    d.text((44, H - 74), main, font=font(33), fill=(255, 255, 255), anchor="lm")
    if sub:
        d.text((44, H - 34), sub, font=font(22), fill=(176, 176, 180),
               anchor="lm")
    return im


def badge(im: Image.Image, text: str, x: int) -> None:
    """比較の左右がどちらなのかを、絵の中に置く。"""
    d = ImageDraw.Draw(im)
    f = font(26)
    tw = d.textlength(text, font=f)
    d.rectangle([x, 24, x + tw + 32, 74], fill=(20, 20, 22))
    d.text((x + 16, 49), text, font=f, fill=(255, 255, 255), anchor="lm")


def wipe(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    x = int(W * t)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([0, 0, x, H], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(14))
    out = Image.composite(b, a, mask)
    if 0 < x < W:
        ImageDraw.Draw(out).line([(x, 0), (x, H)], fill=(255, 150, 40), width=5)
    return out


def title_card(t: float) -> Image.Image:
    im = Image.new("RGB", (W, H), (244, 244, 242))
    d = ImageDraw.Draw(im)
    rows = [("FreePencil2 v2.7", 76), ("線が、出るようになりました", 34)]
    y = int(H * 0.32)
    for i, (s, sz) in enumerate(rows):
        a = max(0.0, min(1.0, (t - i * 0.12) / 0.3))
        if a <= 0:
            continue
        f = font(sz)
        v = int(26 + (1 - a) * 190)
        d.text(((W - d.textlength(s, font=f)) / 2, y + int(24 * (1 - a))), s,
               font=f, fill=(v, v, v))
        y += int(sz * 1.7)
    for i, s in enumerate(["購入者の方は追加費用なしで更新できます",
                           "note.com/megamarsun"]):
        a = max(0.0, min(1.0, (t - 0.42 - i * 0.1) / 0.28))
        if a <= 0:
            continue
        f = font(25)
        v = int(105 + (1 - a) * 135)
        d.text(((W - d.textlength(s, font=f)) / 2, y + 26 + i * 44), s,
               font=f, fill=(v, v, v))
    return im


def cap_section(put, lo_mark: str, hi_mark: str, main: str,
                sub: str, pad_lo: float = 0.6, pad_hi: float = 1.2) -> int:
    """実キャプチャから、印と印のあいだを切り出して足す。

    こちらは本物の画面録画なので、カーソルを描き足したりはしない。
    足すのは字幕だけ。
    """
    cap = OUTROOT / "livecap"
    files = sorted(cap.glob("c*.jpg"))
    if not files:
        return 0
    t0 = json.loads((cap / "start.json").read_text())["t0"]
    times = json.loads((cap / "times.json").read_text())
    marks = {m["label"]: m["t"] - t0
             for m in json.loads((cap / "steps.json").read_text())}
    if lo_mark not in marks or hi_mark not in marks:
        return 0
    lo, hi = marks[lo_mark] - pad_lo, marks[hi_mark] + pad_hi
    n = 0
    for i, f in enumerate(files):
        if not lo <= times[i] <= hi:
            continue
        im = Image.open(f).convert("RGB")
        im = im.crop((0, 22, im.width, im.height))   # タイトルバーを落とす
        k = min(W / im.width, H / im.height)
        fr = Image.new("RGB", (W, H), (24, 24, 26))
        fr.paste(im.resize((round(im.width * k), round(im.height * k)),
                           Image.LANCZOS),
                 ((W - round(im.width * k)) // 2,
                  (H - round(im.height * k)) // 2))
        put(caption(fr, main, sub))
        n += 1
    return n


def build(fps: int) -> int:
    FRAMES.mkdir(parents=True, exist_ok=True)
    for old in FRAMES.glob("*.png"):
        old.unlink()
    n = 0

    def put(im: Image.Image) -> None:
        nonlocal n
        im.save(FRAMES / f"w{n:05d}.png")
        n += 1

    # ---- 1. hero : 回しながら線画 -------------------------------------
    hero = seq(OUTROOT / "v27" / "hero_line")
    for i, p in enumerate(hero):
        im = load(p)
        put(caption(im, "3Dモデルに、ボタン1回で線画",
                    "手で描いた線は1本もありません"))

    # ---- 2. sens : 感度 1.0 と 0.5 を左右で -----------------------------
    a100, a050 = seq(OUTROOT / "v27" / "sens_100"), seq(OUTROOT / "v27" / "sens_050")
    pairs = min(len(a100), len(a050))
    half = W // 2
    for i in range(pairs):
        l = load(a100[i]).crop((half // 2, 0, half // 2 + half, H))
        r = load(a050[i]).crop((half // 2, 0, half // 2 + half, H))
        im = Image.new("RGB", (W, H), (255, 255, 255))
        im.paste(l, (0, 0))
        im.paste(r, (half, 0))
        ImageDraw.Draw(im).line([(half, 0), (half, H)], fill=(210, 210, 210),
                                width=3)
        badge(im, "感度 1.0（v2.6まで）", 28)
        badge(im, "感度 0.5（v2.7 既定）", half + 28)
        put(caption(im, "線にならなかった境界にも、線が出る",
                    "v2.7 は「線の感度」の既定を 0.5 に下げました"))

    # ---- 3. town : 遠景つぶれ軽減 OFF -> ON ----------------------------
    # 効きが強すぎると手前の線まで褪せる。実測で 0.6 はインクが 85% 減り、
    # 絵として悪くなった。使う素材は外から指定し、無ければ区間ごと飛ばす
    off = seq(OUTROOT / "v27_town_off" / "frames")
    on = seq(OUTROOT / TOWN_ON / "frames")
    m = min(len(off), len(on))
    w0, w1 = int(m * 0.42), int(m * 0.66)
    for i in range(m):
        a, b = load(off[i]), load(on[i])
        if i < w0:
            im, main, sub = a, "奥へ行くほど線が潰れて、黒く埋まる", "従来"
        elif i < w1:
            t = (i - w0) / max(w1 - w0, 1)
            im = wipe(a, b, t)
            main, sub = "遠景つぶれ軽減", "線の密度で判定。遠くても空いていれば残す"
        else:
            im, main, sub = b, "遠景つぶれ軽減", "既定は 0。上げた分だけ効きます"
        put(caption(im, main, sub))

    # ---- 4. 実際の操作 (本物の画面録画) --------------------------------
    cap_section(put, "sidebar", "tab", "使い方は、これだけです",
                "N キーでサイドバー → FreePencil タブ", 0.4, 1.0)
    cap_section(put, "run", "done", "155パーツを、5.5秒で自動処理",
                "実際の画面です。進捗バーは ESC で中断できます", 0.6, 2.0)
    cap_section(put, "up", "back", "線の量はあとから動かせます",
                "STEP3 の「線の感度」。下げるほど線が増えます", 0.3, 2.6)

    # ---- 5. title -------------------------------------------------------
    nt = int(fps * 4.0)
    for i in range(nt):
        put(title_card(i / max(nt - 1, 1)))
    return n


def encode(fps: int, count: int) -> None:
    code = (
        "import sys, pathlib\n"
        f"sys.path.insert(0, r'{HERE.parent / 'batch'}')\n"
        "import fp_batch\n"
        f"paths = sorted(pathlib.Path(r'{FRAMES}').glob('w*.png'))\n"
        f"fp_batch.encode_video(paths, pathlib.Path(r'{MP4}'), {fps}, {W}, {H})\n"
    )
    tmp = DST / "_encode.py"
    tmp.write_text(code, encoding="utf-8")
    # Blender は書き出し後に非ゼロで終わることがある。出来たファイルで見る
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python",
                        str(tmp)], capture_output=True)
    tmp.unlink(missing_ok=True)
    if not MP4.exists() or MP4.stat().st_size < 10_000:
        raise SystemExit(f"動画が出来ていない (exit {r.returncode})\n"
                         + r.stderr.decode("utf-8", "replace")[-800:])
    print(f"{MP4}  {MP4.stat().st_size // 1024} KB  "
          f"{count} frames / {count / fps:.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--town-on", default="v27_town_on",
                    help="遠景つぶれ軽減ONの素材フォルダ。空にすると町を外す")
    a = ap.parse_args()
    global TOWN_ON
    TOWN_ON = a.town_on or "__none__"
    DST.mkdir(parents=True, exist_ok=True)
    n = build(a.fps)
    print(f"[v27] {n} frames ({n / a.fps:.1f}s)")
    encode(a.fps, n)


if __name__ == "__main__":
    main()
