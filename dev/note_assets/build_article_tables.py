"""note の記事に貼る表を画像にする。

note は表組みを扱えない。箇条書きに開いて逃げることもできるが、
数値の対比(感度1.0と0.5、角度ごとの領域数)は列が揃っていないと
読めないので、画像にして貼る。

数字は本文と同じものを持つ。ここを直すときは本文も直すこと。

    python dev/note_assets/build_article_tables.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DST = Path(__file__).resolve().parents[2] / "note" / "v27_article" / "img"

W = 1400
PAD = 22                 # セルの左右余白
ROW = 66                 # 行の高さ
FS = 30                  # 本文の字の大きさ
HEAD = (38, 38, 42)
LINE = (208, 208, 210)
ALT = (247, 247, 245)    # 偶数行の下地。行を目で追えるようにする
MARK = (198, 40, 40)     # 注目させたい行の字の色

FONTS_B = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc"]
FONTS_R = [r"C:\Windows\Fonts\YuGothR.ttc", r"C:\Windows\Fonts\meiryo.ttc",
           r"C:\Windows\Fonts\msgothic.ttc"]


def font(size: int, bold: bool = False):
    for p in (FONTS_B if bold else FONTS_R):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def table(name: str, head: list[str], rows: list[list[str]],
          weights: list[float], mark: set[int] | None = None,
          title: str | None = None) -> None:
    """1枚の表を描く。

    weights は列幅の比。数値列は狭く、説明列は広く取る。
    mark に入れた行番号は赤字にして、本文で名指ししている行を目立たせる。
    """
    mark = mark or set()
    top = 0 if title is None else 58
    h = top + ROW * (len(rows) + 1) + 2
    im = Image.new("RGB", (W, h), (255, 255, 255))
    d = ImageDraw.Draw(im)

    if title:
        d.text((PAD, top // 2), title, font=font(32, True), fill=(30, 30, 34),
               anchor="lm")

    total = sum(weights)
    xs, acc = [], 0.0
    for w in weights:
        xs.append(round(acc / total * W))
        acc += w
    xs.append(W)

    d.rectangle([0, top, W, top + ROW], fill=HEAD)
    for i, t in enumerate(head):
        d.text((xs[i] + PAD, top + ROW // 2), t, font=font(FS, True),
               fill=(255, 255, 255), anchor="lm")

    for r, row in enumerate(rows):
        y = top + ROW * (r + 1)
        if r % 2 == 1:
            d.rectangle([0, y, W, y + ROW], fill=ALT)
        col = MARK if r in mark else (30, 30, 34)
        for i, t in enumerate(row):
            d.text((xs[i] + PAD, y + ROW // 2), t,
                   font=font(FS, r in mark), fill=col, anchor="lm")
        d.line([(0, y), (W, y)], fill=LINE)
    d.rectangle([0, top, W - 1, h - 1], outline=LINE)
    im.save(DST / name)


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)

    table("t1_luma.png",
          ["塗った2色の差", "結果"],
          [["色の差 0.248 ／ 明るさの差 0.000", "線が出た"],
           ["色の差 0.067", "線が出なかった"]],
          [1.6, 1.0], mark={0})

    table("t2_sensitivity.png",
          ["モデル", "感度 1.0（v2.6まで）", "感度 0.5（v2.7 既定）"],
          [["戦車", "0.0855", "0.0919"],
           ["メカ", "0.1048", "0.1110"],
           ["帆船", "0.0482", "0.0534"],
           ["カメラ", "0.0894", "0.1004"]],
          [1.0, 1.3, 1.3],
          title="画面に占めるインクの量（多いほど線が多い）")

    table("t3_chamfer.png",
          ["二面角", "本数", "どこの辺か"],
          [["90 度", "8 本", "箱の縦の稜と底"],
           ["79 度", "4 本", ""],
           ["64 度", "4 本", "面取りと上面"],
           ["25.6 度", "4 本", "緩い斜面の境目 ← ここが欲しい線"]],
          [1.0, 0.8, 2.6], mark={3},
          title="面取りした箱の20本の辺を、全部数えた結果")

    table("t4_split.png",
          ["モデル", "25 度", "15 度", "5 度"],
          [["面取りした箱（10面）", "10", "10", "10"],
           ["円柱（34面）", "3", "3", "34"],
           ["スザンヌ・細分適用済み（7,872面）", "5", "146", "2,894"],
           ["UV球（2,048面）", "1", "1", "662"]],
          [2.4, 0.8, 0.8, 1.0], mark={2, 3},
          title="角度を下げると、モデルがいくつの領域に割れるか")

    table("t5_channel.png",
          ["チャンネル", "どこから出る線か"],
          [["深度", "奥行きの差。輪郭と重なり"],
           ["メカ", "面の塗り分け。パネルの継ぎ目"],
           ["ボーン", "ボーンの境目。関節"],
           ["マテリアル", "材質の変わり目"],
           ["生成", "手で塗った指定色"]],
          [1.0, 3.0])

    table("t6_paint.png",
          ["STEP4 で塗る色", "何が起きるか"],
          [["メカカラー", "塗り分けそのものを変える。境目に線が出る"],
           ["マスクカラー", "線を消す"],
           ["ラインカラー", "線を足す"]],
          [1.0, 3.0])

    for p in sorted(DST.glob("t*.png")):
        w, h = Image.open(p).size
        print(f"{p.name:<22} {w}x{h}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
