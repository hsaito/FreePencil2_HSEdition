"""線の強弱を何で決めるか。材料を差し替えて総当たりで比べる。

強弱を付けるには「線に沿って連続に変わるスカラー場」が要る。
eval_survey_passes.py でコンポジタに届く材料を全部出したので、
そのどれが強弱の元として使えるかを、同じ土台の線で比べる。

比べるのは次の5つ。どれも既存のレンダーパスで、追加の計算が要らない。
    DiffDir  光。明るいほど細く。これは検証済み
    AO       くぼみ。奥まったところほど太く
    Mist     奥行き。手前ほど太く
    Normal   面の向き。下を向くほど太く
    影       落ち影の中を太く(2値なので段が2つしかない)

  python dev/note_assets/eval_survey_drivers.py [--src out/survey]
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = Path(__file__).resolve().parent


def _mod(name: str, path: str):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")
bl = _mod("bl", "eval_binary_line.py")
bn = _mod("bn", "eval_best_line.py")

LEVELS = [5, 4, 3, 2, 1]
GAIN = 1.4


def load_gray(p: Path) -> np.ndarray:
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float64) / 255.0
    return a.mean(axis=2)


def apply(base: np.ndarray, field: np.ndarray, invert: bool) -> np.ndarray:
    """暗いほど太い、が既定。invert のときは明るいほど太い。"""
    f = (1.0 - field) if invert else field
    return np.clip(bl.shrink(bn.tiers(base, f, LEVELS)) * GAIN, 0.0, 1.0)


def score(base: np.ndarray, field: np.ndarray, invert: bool) -> tuple:
    f = (1.0 - field) if invert else field
    w = bn.widths(base, f, LEVELS)
    v = apply(base, field, invert)
    lab, nc = ndimage.label(v > 0.15, structure=np.ones((3, 3)))
    on = v > 0.15
    return (max(w) / max(min(w), 1e-9), nc, float((v[on] > 0.85).mean() * 100),
            w, v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "survey"))
    a = ap.parse_args()
    src = Path(a.src)

    ink = 1.0 - mx.load(src / "line.png")
    base = bl.binarize(ink, 0.15)
    lab, nc0 = ndimage.label(base > 0.5, structure=np.ones((3, 3)))
    print(f"土台  インク {base.mean() * 100:.3f}%  連結成分 {nc0}\n")

    v = src / "view"
    drivers = [
        ("光(明るいほど細く)", load_gray(v / "DiffDir0001.png"), False),
        ("くぼみ(奥ほど太く)", load_gray(v / "AO0001.png"), False),
        ("奥行き(手前ほど太く)", load_gray(v / "Mist0001.png"), True),
        ("面の向き", load_gray(v / "Normal0001.png"), False),
        ("落ち影(2値)", load_gray(v / "Shadow0001.png"), False),
    ]
    # 光とくぼみは足せる。人が描くときも「奥まった所は濃く、
    # 光が当たる所は抜く」を同時にやっている
    d = load_gray(v / "DiffDir0001.png")
    ao = load_gray(v / "AO0001.png")
    drivers.append(("光 + くぼみ", np.clip(d * 0.5 + ao * 0.5, 0, 1), False))

    print(f"{'元にする材料':<24}{'強弱':>7}{'成分':>6}{'真っ黒%':>9}   段ごとの幅")
    tiles = []
    for name, f, inv in drivers:
        ratio, nc, blk, w, img = score(base, f, inv)
        print(f"{name:<24}{ratio:6.1f}倍{nc:6d}{blk:8.1f}%   "
              + " / ".join(f"{x:.1f}" for x in w))
        tiles.append((f"{name}  {ratio:.1f}倍", img))

    H, W = tiles[0][1].shape
    x0, y0, x1, y1 = int(W * 0.10), int(H * 0.02), int(W * 0.74), int(H * 0.98)
    cw, ch = x1 - x0, y1 - y0
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cw + 8) + 8, rows * (ch + 32) + 8),
                      (150, 150, 156))
    dr = ImageDraw.Draw(sheet)
    for i, (n, img) in enumerate(tiles):
        px, py = 8 + (i % cols) * (cw + 8), 8 + (i // cols) * (ch + 32)
        sheet.paste(mx.to_img(img[y0:y1, x0:x1]), (px, py))
        dr.text((px + 6, py + ch + 5), n, font=mx.font(22), fill=(20, 20, 22))
    sheet.save(src / "drivers.png")
    print(f"\n{src / 'drivers.png'}")


if __name__ == "__main__":
    main()
