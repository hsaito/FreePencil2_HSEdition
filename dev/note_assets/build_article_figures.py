"""note の新規記事(有料部分)に貼る画像を作る。

記事は表が使えないので、比較は文章と画像で見せる。比較図は
「左右に並べて、それぞれに何の条件かを焼き込む」形に統一する。
note の編集画面ではキャプションを別途打てるが、画像単体で
出回っても意味が通るようにラベルは画像に入れておく。

出力先は note/v27_article/img/。番号は記事本文の【画像N】と対応。

    python dev/note_assets/build_article_figures.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
DST = HERE.parents[1] / "note" / "v27_article" / "img"

WIDTH = 1600          # note の本文幅に対して十分な横幅
BAR = 64              # ラベル帯の高さ
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


def flatten(path: Path, crop_alpha: bool = False) -> Image.Image:
    """透過を白地に合成する。note の本文は白なので黒い箱になるのを防ぐ。"""
    im = Image.open(path).convert("RGBA")
    box = im.getbbox() if crop_alpha else None
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    return im.crop(box) if box else im


def labeled(im: Image.Image, text: str, w: int) -> Image.Image:
    """画像の上にラベル帯を足す。どちらが何なのかを画像だけで示す。"""
    h = round(im.height * w / im.width)
    im = im.resize((w, h), Image.LANCZOS)
    out = Image.new("RGB", (w, h + BAR), (255, 255, 255))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, w, BAR - 1], fill=(38, 38, 42))
    d.text((16, BAR // 2), text, font=font(30), fill=(255, 255, 255),
           anchor="lm")
    out.paste(im, (0, BAR))
    d.rectangle([0, BAR, w - 1, h + BAR - 1], outline=(210, 210, 210))
    return out


def side_by_side(a: Path, b: Path, la: str, lb: str, dst: Path,
                 crop_alpha: bool = False, gap: int = 16) -> None:
    half = (WIDTH - gap) // 2
    ims = [labeled(flatten(p, crop_alpha), t, half)
           for p, t in ((a, la), (b, lb))]
    h = max(i.height for i in ims)
    out = Image.new("RGB", (WIDTH, h), (255, 255, 255))
    out.paste(ims[0], (0, 0))
    out.paste(ims[1], (half + gap, 0))
    out.save(dst)


def stacked(a: Path, b: Path, la: str, lb: str, dst: Path,
            crop_alpha: bool = False, gap: int = 16) -> None:
    """横長の絵は縦に積む。左右に割ると細くなって差が見えない。"""
    ims = [labeled(flatten(p, crop_alpha), t, WIDTH)
           for p, t in ((a, la), (b, lb))]
    h = sum(i.height for i in ims) + gap
    out = Image.new("RGB", (WIDTH, h), (255, 255, 255))
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + gap
    out.save(dst)


def crop_frac(src: Path, dst: Path, box) -> Path:
    """指定した割合の範囲を切り出して一時ファイルに置く。

    等倍では差が分からない比較(細線化など)は、一部を拡大して見せる。
    """
    im = flatten(src)
    w, h = im.size
    im.crop((round(w * box[0]), round(h * box[1]),
             round(w * box[2]), round(h * box[3]))).save(dst)
    return dst


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    tmp = DST / "_tmp"
    tmp.mkdir(exist_ok=True)

    # 1 線はどこから来ているのか
    side_by_side(OUT / "mecha_paint.png", OUT / "mecha_line.png",
                 "自動で付いた頂点カラー", "そこから出てくる線",
                 DST / "01_paint_to_line.png", crop_alpha=True)

    # 2 明るさを変えても線は出ません。
    #    元の検証は5段(明度/色相/彩度/パレット2種)あるが、記事で言いたいのは
    #    「明度差ゼロでも線が出る」の一点なので、色相だけを変えた2段目に絞る。
    #    他の段は挙動を自分で説明しきれなかったので載せない
    hue = (0.0, 120 / 600, 1.0, 240 / 600)
    stacked(crop_frac(OUT / "line_response" / "colors.png",
                      tmp / "hue_c.png", hue),
            crop_frac(OUT / "line_response" / "line.png",
                      tmp / "hue_l.png", hue),
            "塗った色（明度差はどこも 0.000。色相だけが違う）",
            "出た線（15か所の境目のうち14か所に線）",
            DST / "02_line_response.png")

    # 3 感度 1.0 と 0.5。全体の絵では索具の1本1本が潰れて差が見えないので、
    #   マストまわりだけを切り出して並べる
    rig = (0.30, 0.06, 0.66, 0.46)
    side_by_side(crop_frac(OUT / "sens_all" / "ship_s100.png",
                           tmp / "rig_a.png", rig),
                 crop_frac(OUT / "sens_all" / "ship_s050.png",
                           tmp / "rig_b.png", rig),
                 "線の感度 1.0（v2.6まで）", "線の感度 0.5（v2.7 既定）",
                 DST / "03_sensitivity.png")

    # 4 自動判定と、手で 25 度に下げたもの。
    #    全体で見るとインク量は 0.0857 -> 0.0880 の差しかなく、等倍では
    #    ほとんど分からない。増えた画素が最も集中していた車体前部を拡大する
    front = (0.15, 0.58, 0.42, 0.88)
    side_by_side(crop_frac(OUT / "ang" / "auto.png", tmp / "ang_a.png", front),
                 crop_frac(OUT / "ang" / "d25.png", tmp / "ang_b.png", front),
                 "エッジ角度 自動判定", "手動で 25 度",
                 DST / "04_angle.png")

    # 5 遠景つぶれ軽減
    side_by_side(OUT / "farcrush" / "corridor_base.png",
                 OUT / "farcrush" / "corridor_r06.png",
                 "遠景つぶれ軽減 0（OFF）", "効き具合 0.6",
                 DST / "05_farcrush.png", crop_alpha=True)

    # 6 細線化。全体では違いが見えないので中央を拡大する
    box = (0.32, 0.30, 0.68, 0.70)
    stacked(crop_frac(OUT / "ss_effect" / "a_plain1920.png",
                      tmp / "ss_a.png", box),
            crop_frac(OUT / "ss_effect" / "b_ss1920.png",
                      tmp / "ss_b.png", box),
            "2倍レンダ→50%縮小 OFF（中央を拡大）", "ON（同じ範囲）",
            DST / "06_thin_line.png")

    # 7 透過テクスチャ。変換を切ると線が消えることが要点。
    #    上下は無地の背景なので、板が写っている帯だけに詰める
    leaf = (0.0, 0.30, 1.0, 0.80)
    stacked(crop_frac(OUT / "alpha" / "hashed_off_line.png",
                      tmp / "leaf_a.png", leaf),
            crop_frac(OUT / "alpha" / "hashed_on_line.png",
                      tmp / "leaf_b.png", leaf),
            "BLEND→HASHED変換 OFF（左から4枚目に線が無い）",
            "ON（既定・4枚とも線が出る）",
            DST / "07_alpha.png")

    for p in tmp.glob("*.png"):
        p.unlink()
    tmp.rmdir()
    for p in sorted(DST.glob("*.png")):
        w, h = Image.open(p).size
        print(f"{p.name:<24} {w}x{h}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
