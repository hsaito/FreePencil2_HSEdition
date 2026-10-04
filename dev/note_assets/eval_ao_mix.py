"""回したスザンヌに強弱を付けて、AO と光を比べる。

段を切るしきい値は**カット内で固定**する。フレームごとに分位点を
取り直すと、絵が変わるたびにしきい値が動いて線がちらつく
(前回の実測: フレーム間で 26% 振れた)。最初の数フレームから
まとめて決めて、あとは使い回す。

出すもの:
    flat/   強弱なし。基準
    ao/     くぼみで強弱
    light/  カメラ追従の光で強弱
    stability.json  フレーム間のインク量の振れ

  python dev/note_assets/eval_ao_mix.py [--src out/ao_turn] [--write]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent


def _mod(name: str, path: str):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")
bl = _mod("bl", "eval_binary_line.py")

LEVELS = [5, 4, 3, 2, 1]
GAIN = 1.4
BIN = 0.15


def load_field(p: Path) -> np.ndarray:
    """16bitグレーの PNG を 0..1 で読む。"""
    im = Image.open(p)
    a = np.asarray(im, dtype=np.float64)
    if a.ndim == 3:
        a = a[..., :3].mean(axis=2)
    return a / (65535.0 if a.max() > 1.5 and im.mode in ("I;16", "I") else
                (255.0 if a.max() > 1.5 else 1.0))


def base_of(p: Path) -> np.ndarray:
    return bl.binarize(1.0 - mx.load(p), BIN)


def fixed_edges(pairs, n: int) -> list[float]:
    """カット全体から段の境目を1回だけ決める。

    フレームごとに取り直すとしきい値が動いて線がちらつくので、
    使うフレームの線の画素をまとめてから分位点を取る。
    """
    pool = []
    for line, field in pairs:
        b = base_of(line)
        v = load_field(field)[b > 0.5]
        if v.size:
            pool.append(v)
    v = np.concatenate(pool)
    return [float(np.percentile(v, 100.0 * (k + 1) / n)) for k in range(n - 1)]


def weighted(base: np.ndarray, field: np.ndarray,
             edges: list[float]) -> np.ndarray:
    """段ごとに太らせて重ねる。段は線そのものの位置の値で決める。"""
    out = np.zeros_like(base)
    n = len(LEVELS)
    for k, px in enumerate(LEVELS):
        lo = -1e9 if k == 0 else edges[k - 1]
        hi = 1e9 if k == n - 1 else edges[k]
        seg = base * ((field >= lo) & (field < hi))
        out = np.maximum(out, bl.morph(seg, px))
    return np.clip(bl.shrink(out) * GAIN, 0.0, 1.0)


def flat(base: np.ndarray) -> np.ndarray:
    mid = LEVELS[len(LEVELS) // 2]
    return np.clip(bl.shrink(bl.morph(base, mid)) * GAIN, 0.0, 1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "ao_turn"))
    ap.add_argument("--write", action="store_true",
                    help="全フレームの合成画像を書き出す")
    a = ap.parse_args()
    src = Path(a.src)
    lines = sorted((src / "line").glob("f*.png"))
    aos = sorted((src / "ao").glob("f*.png"))
    lts = sorted((src / "light").glob("f*.png"))
    n = min(len(lines), len(aos), len(lts))
    if n == 0:
        raise SystemExit(f"素材が無い: {src}")
    print(f"フレーム {n}")

    # しきい値はカット内で固定。等間隔に選んだフレームから決める
    pick = list(range(0, n, max(n // 8, 1)))
    e_ao = fixed_edges([(lines[i], aos[i]) for i in pick], len(LEVELS))
    e_lt = fixed_edges([(lines[i], lts[i]) for i in pick], len(LEVELS))
    print("段の境目  AO   " + " ".join(f"{x:.4f}" for x in e_ao))
    print("          光   " + " ".join(f"{x:.4f}" for x in e_lt))

    stats = {"flat": [], "ao": [], "light": []}
    comps = {"flat": [], "ao": [], "light": []}
    for k in ("flat", "ao", "light"):
        (src / k).mkdir(parents=True, exist_ok=True)
    for i in range(n):
        b = base_of(lines[i])
        fa = load_field(aos[i])
        fl = load_field(lts[i])
        imgs = {"flat": flat(b), "ao": weighted(b, fa, e_ao),
                "light": weighted(b, fl, e_lt)}
        for k, v in imgs.items():
            stats[k].append(float(v.sum()))
            lab, nc = ndimage.label(v > 0.15, structure=np.ones((3, 3)))
            comps[k].append(nc)
            if a.write:
                mx.to_img(v).save(src / k / f"f{i:04d}.png")

    out = {}
    print(f"\n{'方式':<8}{'平均インク':>12}{'隣り合うフレームの差':>22}"
          f"{'最大':>9}{'連結成分':>10}")
    for k in ("flat", "ao", "light"):
        s = np.array(stats[k])
        d = np.abs(np.diff(s)) / s[:-1] * 100.0
        out[k] = {"mean_ink": float(s.mean()), "step_mean": float(d.mean()),
                  "step_max": float(d.max()), "comp_max": int(max(comps[k]))}
        print(f"{k:<8}{s.mean():12.0f}{d.mean():21.2f}%{d.max():8.2f}%"
              f"{max(comps[k]):10d}")

    (src / "stability.json").write_text(json.dumps(
        {"frames": n, "levels": LEVELS, "gain": GAIN, "bin": BIN,
         "edges_ao": e_ao, "edges_light": e_lt, "stats": out},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{src / 'stability.json'}")


if __name__ == "__main__":
    main()
