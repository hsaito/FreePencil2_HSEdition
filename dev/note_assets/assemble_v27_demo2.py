"""v2.7 の宣伝デモ、作り直し版を1本に組み立てる。

前の版は「見ても欲しくならない」と言われた。直したのは4点。

  1. 冒頭に「線になる瞬間」を置く。陰影のみ -> ワイプ -> 線画
  2. モデルを全部入れ替えた。過去のデモの使い回しをやめる
  3. 白地に黒線。灰色の背景に灰色の陰影をやめる
  4. 被写体を切り出して大きく置く。枠の中で小さいのをやめる

  0.0- 5.0s  hero      陰影 -> ワイプ -> 線画 (回りながら)
  5.0-14.0s  montage   5体。1体1.8秒で切り替え
 14.0-17.5s  操作      実キャプチャ。押した瞬間と結果だけ
 17.5-21.0s  title

    python dev/note_assets/assemble_v27_demo2.py [--fps 24]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
OUTROOT = HERE / "out"
SRC = OUTROOT / "v27b"
DST = OUTROOT / "v27_demo2"
FRAMES = DST / "frames"
MP4 = DST / "freepencil_v27_demo.mp4"
BLENDER = r"C:\blender\blender-4.5.2-windows-x64\blender.exe"

W, H = 1600, 900
BASE = (1600, 900)     # 素材の基準。plain だけ 3200x1800 で出ることがある
PAPER = (255, 255, 255)
MARGIN = 0.035          # 被写体の周りに残す余白(高さに対する割合)

# 尺は BGM(30秒)に合わせて固定する。24fps x 720 = 30.0 秒ちょうど。
#   hero 144 + montage 4x72=288 + 実画面 168 + タイトル 120 = 720
CAP_FRAMES = 168
TITLE_FRAMES = 120
TARGET_FRAMES = 720

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


def seq(d: Path) -> list[Path]:
    return sorted(d.glob("f*.png")) if d.exists() else []


def norm(p: Path) -> Image.Image:
    """基準サイズの RGBA にそろえる。plain は 2倍で出ることがある。"""
    im = Image.open(p).convert("RGBA")
    if im.size != BASE:
        im = im.resize(BASE, Image.LANCZOS)
    return im


def place(im: Image.Image, box, cx: float = 0.66) -> Image.Image:
    """指定の範囲を切り出し、白い紙の上に大きく置く。

    宇宙服のような縦長の被写体を高さに合わせると、16:9 では横が
    2割しか埋まらず、両側が白く空いて小さく見える。被写体は右に寄せ、
    空いた左を文字に使う。cx は被写体の中心の横位置(幅に対する割合)。
    """
    im = im.crop(box)
    bg = Image.new("RGBA", im.size, PAPER + (255,))
    im = Image.alpha_composite(bg, im).convert("RGB")
    k = min(W * 0.52 / im.width, H * (1 - MARGIN * 2) / im.height)
    w, h = max(1, round(im.width * k)), max(1, round(im.height * k))
    out = Image.new("RGB", (W, H), PAPER)
    px = round(W * cx) - w // 2
    out.paste(im.resize((w, h), Image.LANCZOS), (px, (H - h) // 2))
    # 被写体が画面のどこにあるかを返す。ワイプはこの範囲だけ走らせる
    return out, (px, px + w)


def union_box(*ims: Image.Image, pad: int = 24):
    """複数の絵に共通の切り出し範囲。ワイプの前後がずれないようにする。"""
    boxes = [i.getbbox() for i in ims if i.getbbox()]
    if not boxes:
        return (0, 0, BASE[0], BASE[1])
    b = (min(x[0] for x in boxes), min(x[1] for x in boxes),
         max(x[2] for x in boxes), max(x[3] for x in boxes))
    return (max(0, b[0] - pad), max(0, b[1] - pad),
            min(BASE[0], b[2] + pad), min(BASE[1], b[3] + pad))


def caption(im: Image.Image, main: str, sub: str | None = None):
    """左の余白に大きく置く。紙の上なので帯は敷かない。

    被写体を右に寄せた分、ここが空く。小さな字を下に置くだけだと
    画面が間延びするので、主文は大きく取る。
    """
    d = ImageDraw.Draw(im)
    lines = main.split("|")          # 改行は | で区切る
    y = int(H * 0.42) - (len(lines) - 1) * 31
    for i, ln in enumerate(lines):
        d.text((72, y + i * 62), ln, font=font(52), fill=(20, 20, 22),
               anchor="lm")
    if sub:
        d.text((72, y + 62 * (len(lines) - 1) + 52), sub, font=font(25),
               fill=(120, 120, 124), anchor="lm")
    return im


def wipe(a: Image.Image, b: Image.Image, t: float,
         span: tuple[int, int] | None = None) -> Image.Image:
    """左から右へ塗り替える。

    被写体を右に寄せているので、画面の端から端まで掃くと、線が被写体に
    届く前に大半が終わってしまう。被写体の幅だけを掃く。
    """
    x0, x1 = span if span else (0, W)
    x = int(x0 - 30 + (x1 - x0 + 60) * t)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([0, 0, x, H], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(10))
    out = Image.composite(b, a, mask)
    if 4 < x < W - 4:
        ImageDraw.Draw(out).line([(x, 0), (x, H)], fill=(20, 20, 22), width=3)
    return out


def title_card(t: float) -> Image.Image:
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    y = int(H * 0.33)
    for i, (s, sz) in enumerate([("FreePencil2 v2.7", 82),
                                 ("3Dモデルが、線画になります", 34)]):
        a = max(0.0, min(1.0, (t - i * 0.12) / 0.3))
        if a <= 0:
            continue
        f = font(sz)
        v = int(20 + (1 - a) * 200)
        d.text(((W - d.textlength(s, font=f)) / 2, y + int(22 * (1 - a))), s,
               font=f, fill=(v, v, v))
        y += int(sz * 1.7)
    for i, s in enumerate(["Blender 4.2 〜 5.2 対応",
                           "note.com/megamarsun"]):
        a = max(0.0, min(1.0, (t - 0.44 - i * 0.1) / 0.28))
        if a <= 0:
            continue
        f = font(25)
        v = int(105 + (1 - a) * 135)
        d.text(((W - d.textlength(s, font=f)) / 2, y + 22 + i * 44), s,
               font=f, fill=(v, v, v))
    return im


def build(fps: int) -> int:
    FRAMES.mkdir(parents=True, exist_ok=True)
    for old in FRAMES.glob("*.png"):
        old.unlink()
    n = 0

    def put(im: Image.Image) -> None:
        nonlocal n
        im.save(FRAMES / f"d{n:05d}.png")
        n += 1

    # ---- 1. hero : 陰影 -> ワイプ -> 線画 ------------------------------
    plain, line = seq(SRC / "scavenger_plain"), seq(SRC / "scavenger_line")
    m = min(len(plain), len(line))
    w0, w1 = int(m * 0.30), int(m * 0.62)
    for i in range(m):
        a, b = norm(plain[i]), norm(line[i])
        box = union_box(a, b)
        pa, span = place(a, box)
        pb, _ = place(b, box)
        if i < w0:
            im = caption(pa, "3Dモデル", "線は入っていません")
        elif i < w1:
            t = (i - w0) / max(w1 - w0, 1)
            im = caption(wipe(pa, pb, t, span), "ボタンを|1回押す", None)
        else:
            im = caption(pb, "線画に|なりました", "手で描いた線は1本もありません")
        put(im)

    # ---- 2. montage : 5体 ----------------------------------------------
    tags = [("apartment", "建築"), ("generator", "機械"),
            ("hangar", "工業"), ("toytrain", "小物")]
    first = True
    for tag, label in tags:
        fs = seq(SRC / f"{tag}_line")
        for i, p in enumerate(fs):
            im = norm(p)
            put(caption(place(im, union_box(im))[0],
                        "同じ設定のまま|モデルを変えるだけ" if first else label,
                        None))
        first = False

    # ---- 3. 操作 : 実キャプチャから、押した瞬間と結果だけ ----------------
    # BGM に合わせて全体を 30.0 秒ちょうどにするので、この区間は
    # 「何枚出すか」を先に決め、録画の時刻から一番近いコマを選び直す。
    # 録画は 17fps 前後の不定間隔なので、等間隔だと思って拾ってはいけない
    cap = OUTROOT / "livecap"
    files = sorted(cap.glob("c*.jpg"))
    if files:
        t0 = json.loads((cap / "start.json").read_text())["t0"]
        times = json.loads((cap / "times.json").read_text())
        marks = {x["label"]: x["t"] - t0
                 for x in json.loads((cap / "steps.json").read_text())}
        lo, hi = marks["run"] - 1.0, marks["done"] + 3.0
        for k in range(CAP_FRAMES):
            sec = lo + (hi - lo) * k / max(CAP_FRAMES - 1, 1)
            i = min(range(len(times)), key=lambda j: abs(times[j] - sec))
            p = files[i]
            im = Image.open(p).convert("RGB")
            im = im.crop((0, 22, im.width, im.height))
            k = min(W / im.width, H / im.height)
            fr = Image.new("RGB", (W, H), (24, 24, 26))
            fr.paste(im.resize((round(im.width * k), round(im.height * k)),
                               Image.LANCZOS),
                     ((W - round(im.width * k)) // 2,
                      (H - round(im.height * k)) // 2))
            d = ImageDraw.Draw(fr)
            d.text((52, H - 74), "155パーツ、5.5秒。実際の画面です",
                   font=font(34), fill=(255, 255, 255), anchor="lm")
            put(fr)

    # ---- 4. title -------------------------------------------------------
    for i in range(TITLE_FRAMES):
        put(title_card(i / max(TITLE_FRAMES - 1, 1)))
    return n


def encode(fps: int, count: int) -> None:
    code = (
        "import sys, pathlib\n"
        f"sys.path.insert(0, r'{HERE.parent / 'batch'}')\n"
        "import fp_batch\n"
        f"paths = sorted(pathlib.Path(r'{FRAMES}').glob('d*.png'))\n"
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
    a = ap.parse_args()
    DST.mkdir(parents=True, exist_ok=True)
    n = build(a.fps)
    print(f"[demo2] {n} frames ({n / a.fps:.1f}s)")
    if n != TARGET_FRAMES:
        print(f"  ! 想定 {TARGET_FRAMES} 枚 ({TARGET_FRAMES / a.fps:.1f}秒) と"
              f"ずれている。素材の枚数を確認すること")
    encode(a.fps, n)


if __name__ == "__main__":
    main()
