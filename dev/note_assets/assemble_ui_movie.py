"""ui_movie.py が撮った UI 状態を、操作の流れの動画に組み立てる。

本物の画面録画ではない。撮れているのは各操作「後」の静止状態だけなので、
    ・状態と状態のあいだをカーソルの移動でつなぐ
    ・押した瞬間にクリックの波紋を出す
    ・何をしているかを画面下に出す
の3つを合成して、操作しているように見せる。カーソルは Blender の
スクリーンショットには写らないため、ここで描いている。

    python dev/note_assets/assemble_ui_movie.py [--fps 24]
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SRC = HERE / "out" / "uimovie"
OUT = SRC / "frames"
MP4 = SRC / "freepencil_ui.mp4"
BLENDER = r"C:\blender\blender-4.5.2-windows-x64\blender.exe"

# 出力は 16:9。撮影素材は 1982x1198 (約 1.65:1) なので、横に暗い余白を足す
W, H = 1600, 900
BG = (32, 32, 34)

# 素材の中でのウィジェット位置 (1982x1198 のときの値)。
# 撮り直して解像度が変わったら、ここも見直すこと
SRC_W, SRC_H = 1982, 1198
P_TAB = (1966, 335)          # サイドバーの縦タブ「FreePencil」
P_RUN = (1790, 462)          # 「全自動セットアップ (STEP1〜3)」ボタン
P_SENS = (1793, 368)         # STEP3 の「線の感度」スライダー

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


def stage(name: str) -> Image.Image:
    """素材を 16:9 の画面に収める。倍率と余白は全カット共通。"""
    im = Image.open(SRC / name).convert("RGB")
    k = min(W / im.width, H / im.height)
    w, h = round(im.width * k), round(im.height * k)
    out = Image.new("RGB", (W, H), BG)
    out.paste(im.resize((w, h), Image.LANCZOS), ((W - w) // 2, (H - h) // 2))
    return out


def to_screen(pt) -> tuple[int, int]:
    """素材の座標を、貼り付け後の画面座標に直す。"""
    k = min(W / SRC_W, H / SRC_H)
    ox, oy = (W - round(SRC_W * k)) // 2, (H - round(SRC_H * k)) // 2
    return round(pt[0] * k) + ox, round(pt[1] * k) + oy


def cursor(im: Image.Image, pt) -> None:
    """矢印のポインタを描く。白抜きに黒縁で、暗い UI の上でも見える。"""
    x, y = pt
    body = [(x, y), (x, y + 30), (x + 8, y + 22), (x + 14, y + 34),
            (x + 20, y + 31), (x + 14, y + 20), (x + 23, y + 19)]
    d = ImageDraw.Draw(im)
    d.polygon([(a + dx, b + dy) for a, b in body for dx, dy in ((0, 0),)][:0]
              or body, fill=(255, 255, 255), outline=(20, 20, 20))


def ripple(im: Image.Image, pt, t: float) -> None:
    """クリックの波紋。t は 0..1。押した位置を目で追えるようにする。"""
    if not 0.0 <= t <= 1.0:
        return
    x, y = pt
    r = int(12 + 46 * t)
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([x - r, y - r, x + r, y + r],
                                  outline=(255, 170, 40,
                                           int(230 * (1 - t))), width=5)
    im.paste(Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB"),
             (0, 0))


def caption(im: Image.Image, text: str, sub: str | None = None) -> None:
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 108, W, H], fill=(18, 18, 20))
    d.text((44, H - 78), text, font=font(34), fill=(255, 255, 255), anchor="lm")
    if sub:
        d.text((44, H - 38), sub, font=font(23), fill=(178, 178, 182),
               anchor="lm")


def title_card(t: float) -> Image.Image:
    im = Image.new("RGB", (W, H), (244, 244, 242))
    d = ImageDraw.Draw(im)
    lines = [("FreePencil2 v2.7", 74), ("ボタン1回で線画になります", 34)]
    y = int(H * 0.34)
    for i, (s, sz) in enumerate(lines):
        a = max(0.0, min(1.0, (t - i * 0.12) / 0.3))
        if a <= 0:
            continue
        f = font(sz)
        v = int(26 + (1 - a) * 190)
        d.text(((W - d.textlength(s, font=f)) / 2, y + int(24 * (1 - a))), s,
               font=f, fill=(v, v, v))
        y += int(sz * 1.6)
    a = max(0.0, min(1.0, (t - 0.45) / 0.3))
    if a > 0:
        f = font(26)
        s = "note.com/megamarsun"
        v = int(110 + (1 - a) * 130)
        d.text(((W - d.textlength(s, font=f)) / 2, y + 24), s, font=f,
               fill=(v, v, v))
    return im


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def build(fps: int) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    n = 0

    def put(im: Image.Image) -> None:
        nonlocal n
        im.save(OUT / f"u{n:05d}.png")
        n += 1

    def hold(base: str, sec: float, txt: str, sub=None, at=None) -> None:
        for _ in range(int(fps * sec)):
            im = stage(base)
            caption(im, txt, sub)
            if at:
                cursor(im, at)
            put(im)

    def move(base: str, a, b, sec: float, txt: str, sub=None) -> None:
        total = int(fps * sec)
        for i in range(total):
            t = ease(i / max(total - 1, 1))
            im = stage(base)
            caption(im, txt, sub)
            cursor(im, (round(a[0] + (b[0] - a[0]) * t),
                        round(a[1] + (b[1] - a[1]) * t)))
            put(im)

    def click(base: str, at, sec: float, txt: str, sub=None) -> None:
        total = int(fps * sec)
        for i in range(total):
            im = stage(base)
            caption(im, txt, sub)
            ripple(im, at, i / max(total - 1, 1))
            cursor(im, at)
            put(im)

    tab, run, sens = to_screen(P_TAB), to_screen(P_RUN), to_screen(P_SENS)
    start = (W // 2 - 260, H // 2 + 40)

    hold("m0_closed.png", 1.6, "3Dモデルを開いたところ", "線は入っていません")
    move("m0_closed.png", start, tab, 1.0,
         "N キーでサイドバーを出す", "3Dビューポートで N")
    hold("m1_open.png", 0.7, "N キーでサイドバーを出す", "3Dビューポートで N",
         at=tab)
    click("m2_tab.png", tab, 0.9, "FreePencil タブを選ぶ",
          "STEP0〜STEP5 が並びます")
    hold("m2_tab.png", 1.1, "FreePencil タブを選ぶ",
         "STEP0〜STEP5 が並びます", at=tab)
    move("m2_tab.png", tab, run, 0.9, "押すのはここ1か所だけ",
         "STEP0：全自動セットアップ")
    click("m2_tab.png", run, 1.0, "押すのはここ1か所だけ",
          "STEP0：全自動セットアップ")
    hold("m3_done.png", 3.2, "155個のメッシュに線が出ました",
         "塗り分けもノードも自動。手作業はありません", at=run)
    hold("m4_step3.png", 1.4, "STEP3 で線の量を調整できます",
         "「線の感度」はしきい値。下げるほど線が増えます")
    move("m4_step3.png", to_screen((1790, 500)), sens, 0.8,
         "STEP3 で線の量を調整できます",
         "「線の感度」はしきい値。下げるほど線が増えます")
    # 字幕の数字は、ビューポートの白い領域で実測した線の量。
    #   0.5 -> 0.0827 / 1.0 -> 0.0754 / 0.35 -> 0.0861
    # 動画で見ると差が小さいので、数字を添えて何が起きたかを示す
    hold("m5_sens100.png", 2.0, "感度 1.0 ── v2.6 までの既定",
         "線の量 0.0754。線にならない境界が残ります", at=sens)
    hold("m6_sens035.png", 2.0, "感度 0.35 ── 下げると線が増える",
         "線の量 0.0861。密なメカでも破綻しません", at=sens)
    hold("m7_sens050.png", 2.4, "感度 0.5 ── v2.7 の新しい既定",
         "線の量 0.0827。STEP0 が自動で設定します", at=sens)

    n_title = int(fps * 3.4)
    for i in range(n_title):
        put(title_card(i / max(n_title - 1, 1)))
    return n


def encode(fps: int, count: int) -> None:
    code = (
        "import sys, pathlib\n"
        f"sys.path.insert(0, r'{HERE.parent / 'batch'}')\n"
        "import fp_batch\n"
        f"paths = sorted(pathlib.Path(r'{OUT}').glob('u*.png'))\n"
        f"fp_batch.encode_video(paths, pathlib.Path(r'{MP4}'), {fps}, {W}, {H})\n"
    )
    tmp = SRC / "_encode.py"
    tmp.write_text(code, encoding="utf-8")
    # Blender は書き出しに成功しても終了時に非ゼロで落ちることがある。
    # 終了コードではなく出来たファイルで判定する
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
    n = build(a.fps)
    print(f"[ui] {n} frames ({n / a.fps:.1f}s)")
    encode(a.fps, n)


if __name__ == "__main__":
    main()
