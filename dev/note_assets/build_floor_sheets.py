"""eval_floor_ridge_all.py の結果を、目で見るための一覧にする。

数値だけでは「線が減った」以上のことが分からない。減った線が形の情報
だったのか、要らないメッシュの格子だったのかは絵を見ないと判断できない。
変化の大きい順に並べて、いま/提案 を左右に置く。

  python dev/note_assets/build_floor_sheets.py [--src out/floor_all]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def _mod(name: str, path: str):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")


def onwhite(p: Path, size):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB").resize(
        size, Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "floor_all"))
    ap.add_argument("--per-sheet", type=int, default=6)
    a = ap.parse_args()
    src = Path(a.src)
    data = json.loads((src / "all.json").read_text(encoding="utf-8"))
    rows = sorted(data["rows"], key=lambda r: r["d_inside"])

    cw, ch = 470, 264
    n = a.per_sheet
    made = []
    for s in range(0, len(rows), n):
        chunk = rows[s:s + n]
        sheet = Image.new("RGB", (2 * (cw + 6) + 6,
                                  len(chunk) * (ch + 26) + 6), (150, 150, 156))
        d = ImageDraw.Draw(sheet)
        for i, r in enumerate(chunk):
            y = 6 + i * (ch + 26)
            for j, tag in enumerate(("now", "new")):
                p = src / f"{r['model']}_{tag}.png"
                if not p.exists():
                    continue
                sheet.paste(onwhite(p, (cw, ch)), (6 + j * (cw + 6), y))
            d.text((12, y + ch + 4),
                   f"{r['model']}   左=いま(5度/0.25)  右=提案(14度/0.45)   "
                   f"内側 {r['d_inside']:+.1f}%  インク {r['d_ink']:+.1f}%",
                   font=mx.font(17), fill=(20, 20, 22))
        dst = src / f"sheet_{s // n + 1:02d}.png"
        sheet.save(dst)
        made.append(dst)
        print(dst)
    print(f"{len(rows)}体 / {len(made)}枚")


if __name__ == "__main__":
    main()
