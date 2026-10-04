"""eval_style_all.py の結果を、精密 / 強弱 を左右に並べて目で見る一覧にする。

印(flags)の付いた体を先頭に持ってくる。数字は補助で、判断は絵。

  python dev/note_assets/build_style_sheets.py [--src out/style_all]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def _mod(name, path):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")


def onwhite(p: Path, size):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB").resize(size, Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "style_all"))
    ap.add_argument("--per-sheet", type=int, default=6)
    a = ap.parse_args()
    src = Path(a.src)
    data = json.loads((src / "all.json").read_text(encoding="utf-8"))
    rows = sorted(data["rows"], key=lambda r: (not r["flags"], r["model"]))
    cw, ch = 470, 470
    n = a.per_sheet
    for s in range(0, len(rows), n):
        chunk = rows[s:s + n]
        sheet = Image.new("RGB", (2 * (cw + 6) + 6, len(chunk) * (ch + 26) + 6),
                          (150, 150, 156))
        d = ImageDraw.Draw(sheet)
        for i, r in enumerate(chunk):
            y = 6 + i * (ch + 26)
            for j, tag in enumerate(("precise", "weighted")):
                p = src / f"{r['model']}_{tag}.png"
                if p.exists():
                    sheet.paste(onwhite(p, (cw, ch)), (6 + j * (cw + 6), y))
            w = r["weighted"]
            flag = ("  ★" + " / ".join(r["flags"])) if r["flags"] else ""
            d.text((12, y + ch + 4),
                   f"{r['model']}   左=精密(v2.7)  右=強弱   真っ黒 "
                   f"{r['precise']['black_rate']:.0f}→{w['black_rate']:.0f}%{flag}",
                   font=mx.font(16), fill=(20, 20, 22))
        dst = src / f"sheet_{s // n + 1:02d}.png"
        sheet.save(dst)
        print(dst)


if __name__ == "__main__":
    main()
