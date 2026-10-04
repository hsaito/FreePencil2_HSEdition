"""capture_screen.py が録った実キャプチャを mp4 にする。

こちらは本物の画面録画なので、カーソルなどを描き足さない。足すのは
字幕だけ。何が起きているかは画面がそのまま語っている。

録画は取りこぼしがあって等間隔ではないので (実測 17fps 前後)、
出力の fps に合わせて時刻がいちばん近いフレームを選び直す。

    python dev/note_assets/assemble_live_movie.py [--fps 20]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SRC = HERE / "out" / "livecap"
OUT = SRC / "frames"
MP4 = SRC / "freepencil_capture.mp4"
BLENDER = r"C:\blender\blender-4.5.2-windows-x64\blender.exe"

W, H = 1600, 900
TITLEBAR = 22          # 上のタイトルバーは切る。ファイルパスが写るため

# 印ごとの字幕。ui_live.py の mark() と対応する
CAPTIONS = {
    "open":    ("3Dモデルを開いたところ", "線は入っていません"),
    "sidebar": ("N キーでサイドバーを出す", None),
    "tab":     ("FreePencil タブを選ぶ", "STEP0〜STEP5 が並びます"),
    "run":     ("STEP0「全自動セットアップ」を押す", "押すのはここ1か所だけ"),
    "done":    ("155個のメッシュに線が出ました",
                "塗り分けもノードも自動。手作業はありません"),
    "step3":   ("STEP3 で線の量を調整できます",
                "「線の感度」はしきい値です"),
    "up":      ("感度を上げる → 線が減る", "1.0 が v2.6 までの既定"),
    "down":    ("感度を下げる → 線が増える", "0.35 でもメカは破綻しません"),
    "back":    ("既定の 0.5 に戻す", "v2.7 は STEP0 がこれを自動で設定します"),
}

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


def fit(im: Image.Image) -> Image.Image:
    """タイトルバーを落として 16:9 に収める。"""
    im = im.crop((0, TITLEBAR, im.width, im.height))
    k = min(W / im.width, H / im.height)
    w, h = round(im.width * k), round(im.height * k)
    out = Image.new("RGB", (W, H), (24, 24, 26))
    out.paste(im.resize((w, h), Image.LANCZOS), ((W - w) // 2, (H - h) // 2))
    return out


def caption(im: Image.Image, main: str, sub: str | None) -> None:
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 104, W, H], fill=(16, 16, 18))
    d.text((44, H - 74), main, font=font(33), fill=(255, 255, 255), anchor="lm")
    if sub:
        d.text((44, H - 34), sub, font=font(22), fill=(176, 176, 180),
               anchor="lm")


def title_card(t: float) -> Image.Image:
    im = Image.new("RGB", (W, H), (244, 244, 242))
    d = ImageDraw.Draw(im)
    for i, (s, sz) in enumerate([("FreePencil2 v2.7", 74),
                                 ("ボタン1回で線画になります", 34)]):
        a = max(0.0, min(1.0, (t - i * 0.12) / 0.3))
        if a <= 0:
            continue
        f = font(sz)
        v = int(26 + (1 - a) * 190)
        d.text(((W - d.textlength(s, font=f)) / 2,
                int(H * 0.34) + i * 118 + int(24 * (1 - a))), s, font=f,
               fill=(v, v, v))
    a = max(0.0, min(1.0, (t - 0.45) / 0.3))
    if a > 0:
        f, s = font(26), "note.com/megamarsun"
        v = int(110 + (1 - a) * 130)
        d.text(((W - d.textlength(s, font=f)) / 2, int(H * 0.34) + 250), s,
               font=f, fill=(v, v, v))
    return im


def build(fps: int) -> int:
    t0 = json.loads((SRC / "start.json").read_text())["t0"]
    times = json.loads((SRC / "times.json").read_text())
    marks = json.loads((SRC / "steps.json").read_text())
    files = sorted(SRC.glob("c*.jpg"))
    if len(files) != len(times):
        raise SystemExit(f"枚数が合わない: {len(files)} != {len(times)}")

    # 印を録画開始からの秒に直す。最初の印の少し前から始める
    ev = [(m["t"] - t0, m["label"]) for m in marks]
    start = max(0.0, ev[0][0] - 0.6)
    # 最後の印のあと、Blender は掃引 2.1 秒 + 余韻 3.0 秒で終了する。
    # 録画はそこで止まらないので、終わったあとの画面(背後にあった別の
    # ウィンドウ)がそのまま入る。実際に一度入った。必ず手前で切る
    end = min(times[-1], ev[-1][0] + 4.6)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    def label_at(sec: float):
        cur = ev[0][1]
        for t, lab in ev:
            if sec >= t:
                cur = lab
            else:
                break
        return CAPTIONS.get(cur, (None, None))

    n = 0
    j = 0
    total = int((end - start) * fps)
    for i in range(total):
        sec = start + i / fps
        while j + 1 < len(times) and abs(times[j + 1] - sec) <= abs(times[j] - sec):
            j += 1
        im = fit(Image.open(files[j]).convert("RGB"))
        main, sub = label_at(sec)
        if main:
            caption(im, main, sub)
        im.save(OUT / f"v{n:05d}.png")
        n += 1

    for i in range(int(fps * 3.0)):
        title_card(i / max(int(fps * 3.0) - 1, 1)).save(OUT / f"v{n:05d}.png")
        n += 1
    return n


def encode(fps: int, count: int) -> None:
    code = (
        "import sys, pathlib\n"
        f"sys.path.insert(0, r'{HERE.parent / 'batch'}')\n"
        "import fp_batch\n"
        f"paths = sorted(pathlib.Path(r'{OUT}').glob('v*.png'))\n"
        f"fp_batch.encode_video(paths, pathlib.Path(r'{MP4}'), {fps}, {W}, {H})\n"
    )
    tmp = SRC / "_encode.py"
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
    ap.add_argument("--fps", type=int, default=20)
    a = ap.parse_args()
    n = build(a.fps)
    print(f"[live] {n} frames ({n / a.fps:.1f}s)")
    encode(a.fps, n)


if __name__ == "__main__":
    main()
