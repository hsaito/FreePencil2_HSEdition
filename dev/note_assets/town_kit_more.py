"""町の詳細キットの追加分(v4.1: 密度を上げる)。

裏手の高層、各階の電照看板、店先の小物、通りをまたぐ電線の束、歩道橋。
town_kit の部品(MB など)を使う。
"""
from __future__ import annotations

import math

import numpy as np
from mathutils import Matrix

from town_kit import MB, facade_matrix, roof_railing, cooling_unit, billboard, antenna


def tower(cx, cy, w, d, floors, face, rng, idx, pitch=1.2, fh=3.6):
    """裏手の高層: カーテンウォールの格子(方立 1.2m・階ごとの無目・スパンドレル)、
    角の柱、屋上の機器・広告塔・アンテナ。表通りの建物の間から見える空を埋める。"""
    mat, along, depth = facade_matrix(cx, cy, w, d, face)
    mb = MB(f"tower{idx}")
    h = floors * fh
    x0, x1 = -along / 2, along / 2
    mb.box(0, depth / 2, h / 2, along, depth, h)
    for side in range(4):
        W = along if side % 2 == 0 else depth
        D = depth if side % 2 == 0 else along
        mb.push(np.array(Matrix.Translation((0, depth / 2, 0))
                         @ Matrix.Rotation(side * math.pi / 2, 4, "Z")
                         @ Matrix.Translation((0, -D / 2, 0))))
        k = max(2, int(W / pitch))
        for i in range(k + 1):
            mb.box(-W / 2 + i * W / k, -0.06, h / 2, 0.08, 0.12, h)            # 方立
        for fl in range(1, floors):
            mb.box(0, -0.07, fl * fh, W, 0.14, 0.1)                            # 無目
            mb.box(0, -0.03, fl * fh - 0.45, W, 0.06, 0.9)                     # スパンドレル
        for s in (-1, 1):
            mb.box(s * W / 2, -0.15, h / 2, 0.5, 0.3, h)                       # 角の柱
        mb.pop()
    mb.box(0, depth / 2, h + 0.4, along + 0.3, depth + 0.3, 0.8)
    roof_railing(mb, x0 + 0.2, x1 - 0.2, 0.2, depth - 0.2, h + 0.8)
    for _ in range(rng.randint(1, 3)):
        cooling_unit(mb, rng.uniform(x0 + 2, x1 - 2), rng.uniform(2, depth - 2), h + 0.8)
    if rng.random() < 0.6:
        billboard(mb, 0, depth * 0.5, h + 0.8, along * 0.7, rng.uniform(3, 5), rng)
    for _ in range(rng.randint(1, 3)):
        antenna(mb, rng.uniform(x0 + 1, x1 - 1), rng.uniform(1, depth - 1), h + 0.8,
                rng.uniform(3, 7), rng)
    return mb.build(mat)


def floor_signs(mb, x0, x1, floors, fh, rng):
    """各階の小さな電照看板(壁付けの箱・縁・取付け金具)。"""
    for fl in range(1, floors):
        if rng.random() < 0.6:
            w = rng.uniform(1.2, 2.4)
            x = rng.uniform(x0 + w / 2 + 0.2, x1 - w / 2 - 0.2)
            z = fl * fh + 2.75
            mb.box(x, -0.12, z, w, 0.2, 0.42)
            mb.box(x, -0.23, z, w + 0.06, 0.03, 0.48)
            mb.box(x, -0.24, z, w * 0.8, 0.02, 0.18)
            for s in (-1, 1):
                mb.box(x + s * w * 0.4, -0.05, z + 0.25, 0.04, 0.12, 0.1)


def shop_clutter(mb, x0, x1, rng):
    """店先の小物(ローカル y<0 の歩道側): A 型看板、プランター、ケース、コーン。"""
    x = x0 + 0.5
    while x < x1 - 0.5:
        kind = rng.choice(("aframe", "planter", "crates", "cone", None, None))
        y = -rng.uniform(0.3, 0.6)
        if kind == "aframe":
            for s in (-1, 1):
                mb.box_ab((x, y + s * 0.02, 0.0), (x, y + s * 0.25, 0.95), 0.5, 0.03)
            mb.box(x, y + 0.13, 0.6, 0.4, 0.02, 0.4)
        elif kind == "planter":
            mb.box(x, y, 0.25, 0.6, 0.35, 0.5)
            mb.box(x, y, 0.52, 0.64, 0.39, 0.05)
            for i in range(5):
                a = i * 1.2566
                mb.box_ab((x, y, 0.5), (x + 0.25 * math.cos(a), y + 0.15 * math.sin(a), 0.95), 0.03)
        elif kind == "crates":
            for j in range(rng.randint(1, 3)):
                mb.box(x, y, 0.15 + j * 0.3, 0.5, 0.35, 0.28)
                for i in range(3):
                    mb.box(x, y - 0.18, 0.08 + j * 0.3 + i * 0.08, 0.5, 0.01, 0.02)
        elif kind == "cone":
            mb.cyl(x, y, 0.35, 0.16, 0.7, 12, r2=0.02)
            mb.box(x, y, 0.02, 0.38, 0.38, 0.04)
            mb.ring(x, y, 0.4, 0.11, 0.02, 0.06, 12, "z")
        x += rng.uniform(0.8, 1.8)


def cross_cables(mb, poles, ROAD, CURB, rng):
    """通りをまたぐ電線の束: 電柱から向かいの建物の壁へ、高さを変えて数本ずつ。"""
    for (px, py) in poles:
        for _ in range(rng.randint(3, 6)):
            z0 = rng.uniform(8.0, 10.4)
            tx, ty, tz = -(CURB - 0.1), py + rng.uniform(-9, 9), rng.uniform(5.5, 9.5)
            prev = None
            for i in range(7):
                t = i / 6
                p = (px + (tx - px) * t, py + (ty - py) * t,
                     z0 + (tz - z0) * t - 0.5 * 4 * t * (1 - t))
                if prev is not None:
                    mb.cyl_ab(prev, p, 0.012, 4)
                prev = p


def pedestrian_bridge(mb, y, ROAD, WALK, obstacles):
    """歩道橋: 床(桁2本・横桁・床板)、高欄(笠木・縦桟 12cm おき・目隠し板)、
    両側の階段(段・手すり・柱)。階段は歩道の上、+y の向きへ下りる。"""
    z = 5.4
    xa, xb = -(ROAD + 2.2), ROAD + 2.2
    L = xb - xa
    Wd = 2.2
    for s in (-1, 1):
        mb.box(0, y + s * Wd / 2, z - 0.35, L, 0.2, 0.7)                       # 桁
        mb.box(0, y + s * Wd / 2, z - 0.72, L, 0.35, 0.05)
    for i in range(int(L / 1.5) + 1):
        mb.box(xa + i * 1.5, y, z - 0.4, 0.08, Wd, 0.5)                        # 横桁
    for s_ in (-1, 1):                                                         # 桁の補剛材と目地
        yo = y + s_ * (Wd / 2 + 0.11)
        for i in range(int(L / 0.8) + 1):
            mb.box(xa + i * 0.8, yo, z - 0.35, 0.04, 0.03, 0.66)
        for zz in (z - 0.12, z - 0.55):
            mb.box(0, yo + s_ * 0.01, zz, L, 0.02, 0.03)
    for i in range(int(L / 0.5)):                                              # 床板の裏の目地
        mb.box(xa + 0.25 + i * 0.5, y, z - 0.07, 0.03, Wd - 0.4, 0.02)
    mb.box(0, y, z, L, Wd, 0.12)                                               # 床板
    for s in (-1, 1):
        ye = y + s * (Wd / 2 - 0.03)
        mb.box(0, ye, z + 1.15, L, 0.12, 0.08)                                 # 笠木
        mb.box(0, ye, z + 0.15, L, 0.06, 0.08)
        k = int(L / 0.12)
        for i in range(k + 1):
            mb.box(xa + i * L / k, ye, z + 0.65, 0.02, 0.02, 1.0)
        mb.box(0, ye + s * 0.04, z + 0.85, L, 0.02, 0.35)                      # 目隠し板
    mb.box(0, y - Wd / 2 - 0.05, z + 1.6, 3.5, 0.08, 0.6)                      # 橋名板
    for sx in (-1, 1):
        xs = sx * (ROAD + 2.6)
        run = 7.5
        y0, y1 = y + Wd / 2, y + Wd / 2 + run
        for i in range(8):
            obstacles.append((xs, y0 + i * run / 7, 1.0))
        n = int(z / 0.16)
        for i in range(n):
            t = (i + 0.5) / n
            mb.box(xs, y0 + run * t, z * (1 - t), 1.5, run / n + 0.02, 0.05)   # 段
        mb.box_ab((xs, y0, z - 0.25), (xs, y1, -0.1), 1.5, 0.25)               # 段の下の桁
        for s in (-1, 1):
            xr = xs + s * 0.78
            mb.box_ab((xr, y0, z + 1.0), (xr, y1, 1.0), 0.06)                  # 手すり
            k = int(run / 0.25)
            for i in range(k + 1):
                t = i / k
                mb.box(xr, y0 + run * t, z * (1 - t) + 0.5, 0.02, 0.02, 1.0)
        for t in (0.0, 0.5):                                                   # 柱
            mb.box(xs, y0 + run * t + 0.3, z * (1 - t) / 2, 0.25, 0.25, z * (1 - t))
