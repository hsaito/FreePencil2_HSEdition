"""線の重さの規則を、測って見つける実験。

仮説:
    線の太さは「その線が囲んでいる領域の大きさ」で決まる。
    大きな形の輪郭は太く、細部の中の線は細い。

これが成り立つなら、深度チャンネルやメカチャンネルという区分に
頼らずに、線の役割を面積から自動で決められる。外形が太くなるのも
「外形は背景という一番大きな領域に接しているから」で説明がつく。

やること:
    1. 線を2値化する
    2. 線でない画素を連結成分に分ける (= 塗り分けられた領域)
    3. 各線画素について、両隣の領域の面積を調べる
    4. 面積と、いまの線の太さ(深度チャンネルかどうか)の関係を測る
    5. 面積から太さを決めた絵を作って、目で見る

「自分で見つけた規則」と言うためには、4 で実際に相関を出すこと。
出なければ仮説は棄却する。

  python dev/note_assets/eval_region_rule.py --src out/hi_car
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd

HERE = Path(__file__).resolve().parent


def _mod(name: str, path: str):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")
bl = _mod("bl", "eval_binary_line.py")


def region_area_at_line(line_bin: np.ndarray) -> tuple:
    """各線画素に「隣接する領域のうち小さい方の面積」を割り当てる。

    小さい方を採るのは、細部の中の線を細くしたいから。大きな形の輪郭は
    両隣とも大きいので、小さい方も大きい。
    背景も1つの領域として数える(外形が最大になる)。
    """
    free = (line_bin < 0.5)
    lab, n = nd.label(free)
    areas = np.bincount(lab.ravel())
    areas[0] = 0                       # 0 は線そのもの

    # 線画素の周り 3x3 に現れる領域番号を集める。膨張を領域ごとにやると
    # 重いので、最大値と「最大以外の最大」を別々に取る
    big = nd.maximum_filter(lab, size=3)
    # 面積に置き換えてから最小を取る。0(線)は除きたいので大きな値で埋める
    area_map = areas[lab]
    area_map_masked = np.where(free, area_map, areas.max() + 1)
    small = nd.minimum_filter(area_map_masked, size=3)
    big_area = nd.maximum_filter(np.where(free, area_map, 0), size=3)
    return small, big_area, lab, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "hi_car"))
    ap.add_argument("--thresh", type=float, default=0.25)
    a = ap.parse_args()
    src = Path(a.src)

    all_ = 1.0 - mx.load(src / "ch_all.png")
    dep = 1.0 - mx.load(src / "ch_depth.png")
    b_all = bl.binarize(all_, a.thresh)
    b_dep = bl.binarize(dep, a.thresh)

    small, big, lab, n = region_area_at_line(b_all)
    px = b_all > 0.5
    total = b_all.size

    print(f"領域の数 {n}  線の画素 {px.sum()}")
    # 面積は画面全体に対する割合で見る
    s = small[px] / total
    isdep = b_dep[px] > 0.5
    print(f"  うち深度チャンネル由来 {isdep.sum()} ({isdep.mean() * 100:.1f}%)")
    print()
    print("  隣の小さい方の領域が画面に占める割合ごとに、")
    print("  その線が深度チャンネル(=外形)である割合を見る")
    print("    面積帯            線の数   外形である割合")
    edges = [0, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0]
    for i in range(len(edges) - 1):
        m = (s >= edges[i]) & (s < edges[i + 1])
        if m.sum() == 0:
            continue
        print(f"    {edges[i]:.0e} - {edges[i+1]:.0e}   {m.sum():7d}   "
              f"{isdep[m].mean() * 100:5.1f}%")

    # 相関。順位相関で見る(面積は桁が広いので)
    from scipy.stats import spearmanr
    r, p = spearmanr(s, isdep.astype(float))
    print(f"\n  順位相関 (領域の大きさ vs 外形らしさ): r = {r:+.3f}  p = {p:.2e}")


if __name__ == "__main__":
    main()
