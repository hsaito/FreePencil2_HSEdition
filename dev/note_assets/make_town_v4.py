"""町 v4: 詳細キット(town_kit)で作り直した町。区画・車・木・人形は v2 と同じ。

  blender -b --factory-startup --python make_town_v4.py -- [--out out/town_v4] [--no-step0]
      [--only-lot 5]   建物1つだけ作って確かめる(区画の番号)

v2 の建物関数と街路を town_kit のものに差し替えてから、v2 の main を回す。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if "--" not in sys.argv:              # v2 は "--" の後ろだけを引数として読む
    sys.argv.append("--")
if "--out" not in sys.argv:
    sys.argv += ["--out", str(HERE / "out" / "town_v4")]
sys.path.insert(0, str(HERE))
import make_town_v2 as tv          # noqa: E402
import town_kit as kit             # noqa: E402

tv.shophouse = kit.shophouse
tv.apartment = kit.apartment
tv.house = kit.house
tv.konbini = kit.konbini
tv.parking = kit.parking
tv.street = lambda rng: kit.street(rng, tv.ROAD, tv.WALK, tv.CURB, tv.CROSS, tv.XW, tv.OBSTACLES)

_layout = tv.layout


def layout_with_back_row(rng):
    """表通りの区画に加えて、裏手(表の建物の奥)に高層を並べ、建物の間から見える
    空を埋める。表通りに面さないので、人形・車の邪魔はしない。"""
    import town_kit_more as more
    made = _layout(rng)
    idx = 1000
    for sx in (-1, 1):
        face = "-x" if sx > 0 else "+x"
        y = -60.0
        while y < 135.0:
            if abs(y - tv.CROSS[1]) < 14 or abs(y - tv.CROSS[0]) < 12:
                y += 6.0
                continue
            w_ = rng.uniform(12, 20)
            d_ = rng.uniform(12, 18)
            cx = sx * (tv.CURB + 16.0 + rng.uniform(0, 10) + d_ / 2)
            made.append(more.tower(cx, y + w_ / 2, d_, w_, rng.randint(7, 16), face, rng, idx))
            idx += 1
            y += w_ + rng.uniform(2, 6)
    # 通りの突き当たり(北、y 145..190): 高層の壁。以前は白い空が抜けていた
    x = -48.0
    while x < 48.0:
        w_ = rng.uniform(12, 20)
        d_ = rng.uniform(12, 18)
        y0 = rng.uniform(145, 165)
        made.append(more.tower(x + w_ / 2, y0 + d_ / 2, w_, d_, rng.randint(10, 20), "-y", rng, idx))
        idx += 1
        x += w_ + rng.uniform(1, 4)
    return made


tv.layout = layout_with_back_row

if __name__ == "__main__":
    tv.main()
