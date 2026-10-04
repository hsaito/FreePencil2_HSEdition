"""floor_vars の4条件を1枚に並べる。

「14度」と「稜線0.45」のどちらが効いているのかは、両方同時に変えた
絵だけ見ても分からない。片方ずつの絵を横に並べて、eggs_bowl の後退が
どちらの持ち物なのかを目で決める。

  python dev/note_assets/build_vars_sheet.py [--src out/floor_vars]
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
TAGS = [("now", "いま 5度/0.25"), ("f14", "14度/0.25"),
        ("r45", "5度/0.45"), ("new", "提案 14度/0.45")]


def _mod(name, path):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")


def load(p: Path):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return im, Image.alpha_composite(bg, im).convert("RGB")


def inside_ink(im: Image.Image) -> int:
    a = np.asarray(im, dtype=np.float32) / 255.0
    alpha = a[..., 3] > 0.5
    ink = ((1.0 - a[..., :3].mean(axis=2)) > 0.5) & alpha
    inner = alpha.copy()
    for _ in range(6):
        inner = (inner
                 & np.roll(inner, 1, 0) & np.roll(inner, -1, 0)
                 & np.roll(inner, 1, 1) & np.roll(inner, -1, 1))
    return int((ink & inner).sum())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "floor_vars"))
    a = ap.parse_args()
    src = Path(a.src)
    names = sorted({p.name.rsplit("_", 1)[0]
                    for p in src.glob("*_now.png")})
    cw, ch = 360, 202
    sheet = Image.new("RGB", (4 * (cw + 5) + 5, len(names) * (ch + 40) + 5),
                      (150, 150, 156))
    d = ImageDraw.Draw(sheet)
    for i, name in enumerate(names):
        y = 5 + i * (ch + 40)
        base = None
        for j, (tag, label) in enumerate(TAGS):
            p = src / f"{name}_{tag}.png"
            if not p.exists():
                continue
            rgba, flat = load(p)
            v = inside_ink(rgba)
            if base is None:
                base = v
            x = 5 + j * (cw + 5)
            sheet.paste(flat.resize((cw, ch), Image.LANCZOS), (x, y))
            d.text((x + 4, y + ch + 3),
                   f"{label}   内側 {(v - base) / max(base, 1) * 100:+.1f}%",
                   font=mx.font(16), fill=(20, 20, 22))
        d.text((5, y + ch + 22), name, font=mx.font(16), fill=(40, 40, 44))
    dst = src / "vars.png"
    sheet.save(dst)
    print(dst)


if __name__ == "__main__":
    main()
