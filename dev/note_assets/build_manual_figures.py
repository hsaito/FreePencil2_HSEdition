"""マニュアルに載せる図版を作る。

UI のスクリーンショットは 1982x1198 の丸ごとで、サイドバーは右端の
300px ほどしかない。そのまま貼ると本文の幅に対して字が小さすぎて
読めないので、パネルだけを切り出す。

切り出し位置は撮影時の解像度 (-p 0 0 2400 1400) に対する固定値。
撮り直したら crop_panel の座標を見直すこと。

    python dev/note_assets/build_manual_figures.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FIG = HERE.parents[1] / "manual_figures"

# サイドバーの左端。撮影解像度 1982px に対するパネル領域
PANEL_L, PANEL_R = 1645, 1955


def crop_panel(src: Path, dst: Path, top: int, bottom: int) -> None:
    """サイドバーのパネルだけを切り出して、細い枠を付ける。

    枠を付けるのは、白背景の紙の上でパネルの端がどこまでかを
    分かるようにするため。Blender の UI は暗いので枠なしでも
    見えるが、明るいテーマで撮り直したときに効いてくる。
    """
    im = Image.open(src).convert("RGB").crop((PANEL_L, top, PANEL_R, bottom))
    ImageDraw.Draw(im).rectangle([0, 0, im.width - 1, im.height - 1],
                                 outline=(120, 120, 120))
    im.save(dst)


def on_white(path: Path, box) -> Image.Image:
    """透過つきレンダを白地に合成し、被写体の範囲だけに切り詰める。

    元は背景が透明(保存すると黒)なので、そのまま紙に置くと黒い箱が
    2つ並ぶことになる。線画は白い面に黒い線なので、白地に置いても
    輪郭線でシルエットが読める。
    """
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB").crop(box)


def pair(left: Path, right: Path, dst: Path, gap: int = 40,
         height: int = 620, margin: int = 24) -> None:
    """2枚を横に並べる。切り出す範囲は両方の和にして、大きさを揃える。"""
    boxes = [Image.open(p).getbbox() for p in (left, right)]
    box = (min(b[0] for b in boxes) - margin, min(b[1] for b in boxes) - margin,
           max(b[2] for b in boxes) + margin, max(b[3] for b in boxes) + margin)
    ims = []
    for p in (left, right):
        im = on_white(p, box)
        w = round(im.width * height / im.height)
        ims.append(im.resize((w, height), Image.LANCZOS))
    total = sum(i.width for i in ims) + gap
    out = Image.new("RGB", (total, height), (255, 255, 255))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + gap
    # 2枚の境目に細い縦線。白地どうしなので、無いとどこで切れるか分からない
    ImageDraw.Draw(out).line([(ims[0].width + gap // 2, 0),
                              (ims[0].width + gap // 2, height)],
                             fill=(200, 200, 200))
    out.save(dst)


def shrink(src: Path, dst: Path, width: int) -> None:
    im = Image.open(src).convert("RGB")
    im.resize((width, round(im.height * width / im.width)),
              Image.LANCZOS).save(dst)


def main() -> None:
    FIG.mkdir(exist_ok=True)
    ui = OUT / "ui27"

    # 1. サイドバー全体。「N キーで出るのはこれ」を示す1枚なので、
    #    ビューポートごと入れて位置関係が分かるようにする。
    #    この大きさではパネルの字は読めないが、それはこの図の役目ではない
    #    (中身は図4・図5で拡大する)。どこを見ればいいかだけ枠で示す
    loc = Image.open(ui / "10_ui_sidebar_step0.png").convert("RGB")
    d = ImageDraw.Draw(loc)
    d.rectangle([PANEL_L - 8, 60, PANEL_R + 8, 648],
                outline=(255, 96, 0), width=6)
    loc.resize((1400, round(loc.height * 1400 / loc.width)),
               Image.LANCZOS).save(FIG / "01_sidebar.png")

    # 2. STEP0 のオプション。チェックの一覧が読める必要がある
    crop_panel(ui / "10_ui_sidebar_step0.png", FIG / "02_step0.png", 68, 640)

    # 3. STEP3。線の感度 0.50 が見えることがこの図の目的
    crop_panel(ui / "11_ui_step3.png", FIG / "03_step3.png", 68, 700)

    # 4. プリファレンス (インストール直後の確認)。
    #    画面の下 6 割は空の一覧で、縮めると何も読めない帯になる。
    #    左の分類と、検索欄と、目的の1行が入る高さだけを残す
    pref = Image.open(ui / "12_ui_preferences.png").convert("RGB")
    pref.crop((0, 0, pref.width, 560)).resize(
        (1400, round(560 * 1400 / pref.width)), Image.LANCZOS).save(
            FIG / "04_preferences.png")

    # 5. 塗り分けと線の対。この2枚が並んでいることが仕組みの説明になる
    pair(OUT / "tank_paint.png", OUT / "tank_line.png",
         FIG / "05_paint_to_line.png")

    # 6. アルファで抜いたテクスチャ
    shrink(OUT / "alpha" / "hashed_on_line.png", FIG / "06_alpha.png", 1400)

    for p in sorted(FIG.glob("*.png")):
        w, h = Image.open(p).size
        print(f"{p.name:<24} {w}x{h}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
