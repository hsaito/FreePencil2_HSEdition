"""町の詳細キット(v4)。建物と街路を、車と同じくらいの細かさで作る。

make_town_v2 の建物関数と同じ引数で呼べる(cx, cy, w, d, [floors], face, rng, idx)。
区画割り・車・木・人形・カメラは make_town_v2 / shoot_town_v2 をそのまま使う。

作り方:
  - 部品は bpy.ops で1つずつ足さず、頂点と面を配列に貯めて最後に1つのメッシュに
    する(MB)。v2 の Parts は箱1つに 3ms かかり、細部を増やせなかった
  - 建物は「正面を -y、横が x、奥が +y、地面が z=0、正面の中心が原点」の
    ローカル座標で作り、置くときにオブジェクトの行列で回す

密度の目安は AKIRA の町並み: 窓枠・室外機・ベランダの縦桟・袖看板・シャッター・
配管・給水塔・広告塔・電線・高架道路。線が詰まってもつぶれないかを見るための町。
"""
from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- メッシュを貯める


class MB:
    """頂点と面を貯めて、最後に1つのメッシュにする。

    座標はいまの変換(push で重ねる)を掛けてから貯める。
    """

    def __init__(self, name):
        self.name = name
        self.V = []
        self.F = []
        self.n = 0
        self.M = [np.eye(4)]

    # 変換
    def push(self, m):
        self.M.append(self.M[-1] @ np.asarray(m, dtype=float))

    def pop(self):
        self.M.pop()

    def _add(self, V, F):
        V = np.asarray(V, dtype=float)
        M = self.M[-1]
        V = V @ M[:3, :3].T + M[:3, 3]
        self.V.append(V)
        n = self.n
        self.F.extend([tuple(i + n for i in f) for f in F])
        self.n += len(V)

    # 形
    _BOX_F = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))

    def box(self, cx, cy, cz, sx, sy, sz):
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        V = [(cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
             (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),
             (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
             (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz)]
        self._add(V, self._BOX_F)

    def box_ab(self, a, b, w, h=None):
        """a から b へ伸びる角材(断面 w x h)。"""
        h = w if h is None else h
        a, b = Vector(a), Vector(b)
        d = b - a
        L = d.length
        if L < 1e-6:
            return
        q = d.to_track_quat("Z", "Y")
        m = (Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())
        self.push(np.array(m))
        self.box(0, 0, 0, w, h, L)
        self.pop()

    def cyl(self, cx, cy, cz, r, h, n=8, r2=None):
        """z 向きの円柱(r2 で上をすぼめる)。"""
        r2 = r if r2 is None else r2
        V = []
        for k in range(n):
            a = 2 * math.pi * k / n
            V.append((cx + r * math.cos(a), cy + r * math.sin(a), cz - h / 2))
        for k in range(n):
            a = 2 * math.pi * k / n
            V.append((cx + r2 * math.cos(a), cy + r2 * math.sin(a), cz + h / 2))
        F = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        for k in range(n):
            j = (k + 1) % n
            F.append((k, j, n + j, n + k))
        self._add(V, F)

    def cyl_ab(self, a, b, r, n=6):
        a, b = Vector(a), Vector(b)
        d = b - a
        L = d.length
        if L < 1e-6:
            return
        q = d.to_track_quat("Z", "Y")
        self.push(np.array(Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4()))
        self.cyl(0, 0, 0, r, L, n)
        self.pop()

    def ring(self, cx, cy, cz, R, t, w, n=16, axis="y"):
        """平たい輪(外径 R、帯の幅 t、厚み w)。axis は輪の軸。"""
        rot = {"z": Matrix.Identity(4),
               "y": Matrix.Rotation(math.pi / 2, 4, "X"),
               "x": Matrix.Rotation(math.pi / 2, 4, "Y")}[axis]
        self.push(np.array(Matrix.Translation((cx, cy, cz)) @ rot))
        V = []
        for zz in (-w / 2, w / 2):
            for rr in (R, R - t):
                for k in range(n):
                    a = 2 * math.pi * k / n
                    V.append((rr * math.cos(a), rr * math.sin(a), zz))
        F = []
        o_b, i_b, o_t, i_t = 0, n, 2 * n, 3 * n
        for k in range(n):
            j = (k + 1) % n
            F.append((o_b + k, o_b + j, o_t + j, o_t + k))         # 外周
            F.append((i_b + j, i_b + k, i_t + k, i_t + j))         # 内周
            F.append((o_t + k, o_t + j, i_t + j, i_t + k))         # 上
            F.append((o_b + j, o_b + k, i_b + k, i_b + j))         # 下
        self._add(V, F)
        self.pop()

    def prism(self, x0, x1, y0, y1, z0, z1):
        """切妻屋根(棟は x 方向、y0..y1 の真ん中)。"""
        ym = (y0 + y1) / 2
        V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, ym, z1), (x1, ym, z1)]
        F = [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)]
        self._add(V, F)

    # 仕上げ
    def build(self, matrix=None):
        if not self.V:
            return None
        V = np.concatenate(self.V).astype(np.float32)
        me = bpy.data.meshes.new(self.name)
        me.vertices.add(len(V))
        me.vertices.foreach_set("co", V.ravel())
        loop_total = np.fromiter((len(f) for f in self.F), dtype=np.int32, count=len(self.F))
        loop_start = np.zeros(len(self.F), dtype=np.int32)
        loop_start[1:] = np.cumsum(loop_total)[:-1]
        idx = np.fromiter((i for f in self.F for i in f), dtype=np.int32)
        me.loops.add(len(idx))
        me.loops.foreach_set("vertex_index", idx)
        me.polygons.add(len(self.F))
        me.polygons.foreach_set("loop_start", loop_start)
        me.polygons.foreach_set("loop_total", loop_total)
        me.update(calc_edges=True)
        me.validate(clean_customdata=False)
        # 4.1 以降、配列から作った面は既定でなめらか表示になり、箱が丸い管に
        # 見えた(実測)。全部を平らにする
        me.polygons.foreach_set("use_smooth", np.zeros(len(self.F), dtype=bool))
        me.update()
        o = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(o)
        if matrix is not None:
            o.matrix_world = matrix
        return o


# ---------------------------------------------------------------- 置き方

def facade_matrix(cx, cy, w, d, face):
    """ローカル(正面 -y、原点=正面の中心・地面)-> ワールド。戻り値 (行列, 正面幅, 奥行き)。"""
    n = {"-x": (-1, 0), "+x": (1, 0), "-y": (0, -1), "+y": (0, 1)}[face]
    along, depth = (d, w) if face in ("-x", "+x") else (w, d)
    th = math.atan2(n[0], -n[1])
    org = Vector((cx + n[0] * depth / 2, cy + n[1] * depth / 2, 0.0))
    return Matrix.Translation(org) @ Matrix.Rotation(th, 4, "Z"), along, depth


# ---------------------------------------------------------------- 正面の部品(ローカル)

def window(mb, x, z, w, h, rng, grille=False, blinds=None, sill=True):
    """窓: 額縁(4本)、方立、無目、ガラス(奥)、水切り。ときどきブラインドか面格子。"""
    t, dp = 0.06, 0.10
    y = -0.03
    mb.box(x, y, z + h / 2, w + 2 * t, dp, t)                     # 上枠
    mb.box(x, y, z - h / 2, w + 2 * t, dp, t)                     # 下枠
    mb.box(x - w / 2, y, z, t, dp, h)                             # 縦枠
    mb.box(x + w / 2, y, z, t, dp, h)
    mb.box(x, 0.05, z, w, 0.02, h)                                # ガラス(奥)
    if w > 1.0:
        mb.box(x, y + 0.01, z, 0.04, 0.06, h)                     # 引き違いの召し合わせ
    if h > 1.3:
        mb.box(x, y + 0.01, z + h * 0.22, w, 0.05, 0.04)          # 無目
    if sill:
        mb.box(x, -0.10, z - h / 2 - 0.05, w + 0.24, 0.20, 0.05)  # 水切り
    if blinds is None:
        blinds = rng.random() < 0.3
    if blinds:
        k = int(h / 0.09)
        for i in range(k):
            mb.box(x, 0.03, z - h / 2 + (i + 0.5) * h / k, w - 0.04, 0.015, 0.02)
    if grille:
        k = max(3, int(w / 0.12))
        for i in range(k + 1):
            mb.box(x - w / 2 + i * w / k, -0.12, z, 0.02, 0.02, h)
        for zz in (z - h / 2 + 0.1, z + h / 2 - 0.1):
            mb.box(x, -0.12, zz, w, 0.03, 0.03)


def ac_unit(mb, x, y, z, facing=-1):
    """室外機: 箱、ファンの格子(輪+放射4本)、側面のフィン、脚、配管。facing は正面の y 向き。"""
    W, D, H = 0.80, 0.30, 0.56
    mb.box(x, y, z, W, D, H)
    fy = y + facing * (D / 2 + 0.01)
    mb.ring(x - 0.1, fy, z, 0.21, 0.025, 0.02, 16, "y")
    mb.ring(x - 0.1, fy, z, 0.11, 0.02, 0.02, 12, "y")
    for a in (0, 45, 90, 135):
        r = math.radians(a)
        dx, dz = 0.2 * math.cos(r), 0.2 * math.sin(r)
        mb.box_ab((x - 0.1 - dx, fy, z - dz), (x - 0.1 + dx, fy, z + dz), 0.015)
    for i in range(6):
        mb.box(x + 0.26, fy, z - 0.2 + i * 0.08, 0.18, 0.015, 0.02)
    for s in (-1, 1):
        mb.box(x + s * 0.3, y, z - H / 2 - 0.05, 0.06, D + 0.04, 0.1)
    mb.cyl_ab((x + 0.36, y - facing * 0.1, z - 0.1), (x + 0.36, y - facing * 0.3, z - 0.6), 0.025, 6)


def balcony(mb, x0, x1, z, depth, rng, partition=True, units=0):
    """ベランダ: 床、手すり(笠木+下桟+縦桟 11cm おき)、横の手すり、仕切り板、室外機。"""
    xm, L = (x0 + x1) / 2, x1 - x0
    yf = -depth
    mb.box(xm, -depth / 2, z - 0.08, L, depth, 0.16)                    # 床
    mb.box(xm, yf + 0.04, z - 0.22, L, 0.08, 0.12)                      # 鼻先
    top = z + 1.1
    mb.box(xm, yf + 0.03, top, L, 0.08, 0.05)                           # 笠木
    mb.box(xm, yf + 0.03, z + 0.1, L, 0.04, 0.04)                       # 下桟
    k = max(2, int(L / 0.11))
    for i in range(k + 1):
        mb.box(x0 + i * L / k, yf + 0.03, (z + 0.1 + top) / 2, 0.018, 0.018, top - z - 0.1)
    for xs in (x0, x1):
        mb.box(xs, -depth / 2, top, 0.05, depth, 0.05)
        mb.box(xs, -depth / 2, z + 0.55, 0.03, depth, 0.03)
    if partition and L > 3.0:
        mb.box(x0 + 0.02, -depth / 2, z + 0.9, 0.04, depth - 0.1, 1.8)
    for u in range(units):
        ax = x0 + L * (0.2 + 0.6 * rng.random())
        ac_unit(mb, ax, yf + 0.3, z + 0.33, -1)
    if rng.random() < 0.5:                                               # 物干し竿
        for s in (-1, 1):
            mb.box(xm + s * L * 0.35, yf + 0.25, top + 0.3, 0.03, 0.3, 0.03)
        mb.cyl_ab((x0 + 0.2, yf + 0.25, top + 0.3), (x1 - 0.2, yf + 0.25, top + 0.3), 0.015, 6)


def drain_pipe(mb, x, y, z0, z1):
    """竪樋: 管、1m ごとの留め金具、上の集水器。"""
    mb.cyl(x, y, (z0 + z1) / 2, 0.05, z1 - z0, 8)
    z = z0 + 0.5
    while z < z1 - 0.3:
        mb.box(x, y + 0.05, z, 0.16, 0.1, 0.04)
        z += 1.0
    mb.box(x, y, z1, 0.22, 0.2, 0.25)


def meter_box(mb, x, z):
    mb.box(x, -0.08, z, 0.35, 0.16, 0.45)
    mb.box(x, -0.17, z + 0.05, 0.25, 0.02, 0.25)
    mb.cyl_ab((x, -0.08, z - 0.22), (x, -0.08, 0.0), 0.02, 6)


def shutter(mb, x, w, h, open_frac=0.0):
    """シャッター: スラット 8cm おき、ガイドレール、上のシャッターボックス。"""
    z_bot = h * open_frac
    k = int((h - z_bot) / 0.08)
    for i in range(k):
        mb.box(x, -0.06, h - (i + 0.5) * 0.08, w, 0.03, 0.05)
    for s in (-1, 1):
        mb.box(x + s * (w / 2 + 0.04), -0.07, h / 2, 0.08, 0.1, h)
    mb.box(x, -0.18, h + 0.2, w + 0.3, 0.36, 0.4)
    mb.box(x, -0.07, z_bot + 0.03, w, 0.06, 0.06)                     # 座板


def sign_stack(mb, x, z0, z1, rng, out=1.2):
    """袖看板の塔: 通りへ突き出す縦長の枠に、階ごとの看板板、ブラケット、照明。"""
    W, T = 0.9, 0.28
    yc = -out / 2 - 0.15
    mb.box(x, yc, (z0 + z1) / 2, 0.08, out, z1 - z0)                   # 背骨(壁側の縦材)
    n = max(2, int((z1 - z0) / 1.2))
    ph = (z1 - z0) / n
    for i in range(n):
        zc = z0 + (i + 0.5) * ph
        mb.box(x, -out + 0.1, zc, T, W, ph - 0.12)                     # 看板板
        mb.box(x, -out + 0.1, zc + ph / 2 - 0.08, T + 0.06, W + 0.06, 0.04)
        mb.box(x, -out + 0.1, zc - ph / 2 + 0.08, T + 0.06, W + 0.06, 0.04)
        for s in (-1, 1):                                               # 文字の段(帯)
            mb.box(x + s * (T / 2 + 0.005), -out + 0.1, zc, 0.01, W * 0.7, ph * 0.08)
        mb.box_ab((x, -0.1, zc + ph * 0.3), (x, -out + 0.5, zc + ph * 0.45), 0.04)    # ブラケット
        mb.box_ab((x, -0.1, zc - ph * 0.3), (x, -out + 0.5, zc - ph * 0.45), 0.04)
    mb.box(x, -out + 0.1, z1 + 0.15, 0.12, 0.5, 0.12)                  # 上の照明
    mb.box_ab((x, -out + 0.1, z1 + 0.1), (x, -out - 0.4, z1 + 0.4), 0.03)


def roof_railing(mb, x0, x1, y0, y1, z, h=1.1):
    for (a, b) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        mb.box_ab((a[0], a[1], z + h), (b[0], b[1], z + h), 0.04)
        mb.box_ab((a[0], a[1], z + h * 0.5), (b[0], b[1], z + h * 0.5), 0.03)
        k = max(1, int(L / 1.5))
        for i in range(k + 1):
            t = i / k
            mb.box(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, z + h / 2, 0.05, 0.05, h)


def water_tank(mb, x, y, z, rng):
    """給水塔: 架台(脚4・横つなぎ・筋交い)、タンク、はしご、上の点検口。"""
    r = rng.uniform(0.8, 1.2)
    hh = rng.uniform(1.2, 1.8)
    leg = rng.uniform(1.2, 2.2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.box(x + sx * r * 0.8, y + sy * r * 0.8, z + leg / 2, 0.1, 0.1, leg)
    for (a, b) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
        pa = (x + a[0] * r * 0.8, y + a[1] * r * 0.8)
        pb = (x + b[0] * r * 0.8, y + b[1] * r * 0.8)
        mb.box_ab((pa[0], pa[1], z + leg * 0.5), (pb[0], pb[1], z + leg * 0.5), 0.06)
        mb.box_ab((pa[0], pa[1], z + 0.1), (pb[0], pb[1], z + leg), 0.04)       # 筋交い
    mb.box(x, y, z + leg + 0.05, r * 2, r * 2, 0.1)
    mb.cyl(x, y, z + leg + 0.1 + hh / 2, r, hh, 16)
    mb.cyl(x, y, z + leg + 0.1 + hh + 0.05, r * 0.3, 0.1, 10)
    for i in range(3):                                                   # たが
        mb.ring(x, y, z + leg + 0.1 + hh * (i + 1) / 4, r + 0.03, 0.04, 0.05, 16, "z")
    lx = x + r + 0.12
    for s in (-1, 1):
        mb.box(lx, y + s * 0.2, z + (leg + hh) / 2 + 0.1, 0.04, 0.04, leg + hh + 0.2)
    k = int((leg + hh) / 0.3)
    for i in range(k):
        mb.box(lx, y, z + 0.3 + i * 0.3, 0.03, 0.4, 0.03)


def antenna(mb, x, y, z, h, rng):
    mb.box(x, y, z + h / 2, 0.06, 0.06, h)
    for i in range(rng.randint(2, 4)):
        zz = z + h * (0.55 + 0.13 * i)
        L = rng.uniform(0.6, 1.2)
        mb.box(x, y, zz, L, 0.03, 0.03)
        for j in range(5):                                               # 八木の素子
            mb.box(x - L / 2 + j * L / 4, y, zz, 0.02, 0.35 - 0.04 * j, 0.02)
    for a in (0, 120, 240):                                              # 支線
        r = math.radians(a)
        mb.cyl_ab((x, y, z + h * 0.7), (x + 1.2 * math.cos(r), y + 1.2 * math.sin(r), z), 0.008, 4)


def billboard(mb, x, y, z, w, h, rng):
    """屋上の広告塔: トラスの架台(縦・横・筋交い)、看板面と縁、照明の腕。"""
    frame_h = rng.uniform(1.5, 3.0)
    nx = max(2, int(w / 1.5))
    for i in range(nx + 1):
        xx = x - w / 2 + i * w / nx
        mb.box(xx, y + 0.6, z + frame_h / 2, 0.08, 0.08, frame_h)
        mb.box(xx, y, z + (frame_h + h) / 2, 0.1, 0.1, frame_h + h)
        mb.box_ab((xx, y + 0.6, z), (xx, y, z + frame_h), 0.05)
    for zz in (z + 0.2, z + frame_h * 0.5, z + frame_h):
        mb.box(x, y + 0.3, zz, w, 0.6, 0.05)
    for i in range(nx):
        xa = x - w / 2 + i * w / nx
        mb.box_ab((xa, y + 0.6, z + 0.2), (xa + w / nx, y + 0.6, z + frame_h), 0.04)
    mb.box(x, y - 0.1, z + frame_h + h / 2, w, 0.12, h)                  # 看板面
    for zz in (z + frame_h, z + frame_h + h):
        mb.box(x, y - 0.18, zz, w + 0.1, 0.06, 0.08)
    for xx in (x - w / 2, x + w / 2):
        mb.box(xx, y - 0.18, z + frame_h + h / 2, 0.08, 0.06, h)
    for i in range(nx):                                                  # 照明の腕
        xx = x - w / 2 + (i + 0.5) * w / nx
        mb.box_ab((xx, y - 0.15, z + frame_h + h + 0.05), (xx, y - 0.9, z + frame_h + h + 0.4), 0.03)
        mb.box(xx, y - 0.95, z + frame_h + h + 0.35, 0.25, 0.15, 0.1)


def cooling_unit(mb, x, y, z):
    """屋上の冷却塔: 箱、上のファン(輪)、側面のルーバー。"""
    mb.box(x, y, z + 0.8, 2.0, 1.4, 1.6)
    mb.ring(x, y, z + 1.65, 0.55, 0.08, 0.1, 20, "z")
    mb.cyl(x, y, z + 1.62, 0.1, 0.1, 8)
    for i in range(10):
        mb.box(x, y - 0.71, z + 0.15 + i * 0.13, 1.8, 0.03, 0.05)
    mb.cyl_ab((x + 1.0, y, z + 0.4), (x + 1.8, y, z + 0.4), 0.08, 8)


def fire_escape(mb, xs, y0, y1, floors, fh, facing_x):
    """外階段(側面): 各階の踊り場(床+手すり)とつなぐ斜めの段、手すり。xs は壁の x。"""
    out = facing_x * 1.2
    xm = xs + out / 2
    for fl in range(1, floors):
        z = fl * fh
        mb.box(xm, (y0 + y1) / 2, z - 0.05, abs(out), y1 - y0, 0.1)
        for yy in (y0, y1):
            mb.box(xs + out, yy, z + 0.55, 0.04, 0.04, 1.1)
        mb.box(xs + out, (y0 + y1) / 2, z + 1.1, 0.04, y1 - y0, 0.04)
        mb.box(xs + out, (y0 + y1) / 2, z + 0.55, 0.03, y1 - y0, 0.03)
        k = int((y1 - y0) / 0.25)
        for i in range(k):
            mb.box(xs + out, y0 + (i + 0.5) * (y1 - y0) / k, z + 0.55, 0.015, 0.015, 1.1)
        # 下の階からの段(斜め)
        za = z - fh
        ya, yb = (y0, y1) if fl % 2 else (y1, y0)
        mb.box_ab((xm, ya, za + 0.05), (xm, yb, z - 0.1), 0.9, 0.08)
        steps = int(fh / 0.2)
        for i in range(steps):
            t = (i + 0.5) / steps
            mb.box(xm, ya + (yb - ya) * t, za + (z - za) * t, 0.9, 0.04, 0.12)
        mb.box_ab((xs + out, ya, za + 1.0), (xs + out, yb, z + 1.0), 0.04)


# ---------------------------------------------------------------- 建物

def shophouse(cx, cy, w, d, floors, face, rng, idx):
    """雑居ビル: 1階は店(シャッター半開き・看板帯・庇)、上は窓と室外機、袖看板の塔、
    屋上に給水塔・広告塔・アンテナ・手すり、側面に配管と外階段。"""
    floors = floors + rng.choice((2, 3, 4, 5))               # v2 より高く(谷のような通りにする)
    mat, along, depth = facade_matrix(cx, cy, w, d, face)
    mb = MB(f"shop{idx}")
    fh = 3.2
    h = floors * fh + 0.6
    x0, x1 = -along / 2, along / 2
    mb.box(0, depth / 2, h / 2, along, depth, h)                          # 躯体
    for fl in range(1, floors + 1):                                        # 階の目地(帯)
        mb.box(0, -0.04, fl * fh, along + 0.1, 0.08, 0.12)
    # 1階: 店
    gw = along - 1.2
    open_frac = rng.choice((0.0, 0.55, 0.75, 1.0))
    if open_frac < 1.0:
        shutter(mb, 0, gw, 2.7, open_frac)
    if open_frac > 0.0:
        mb.box(0, 0.35, 1.35, gw, 0.04, 2.7)                               # 奥のガラス
        k = max(2, int(gw / 1.0))
        for i in range(k + 1):
            mb.box(-gw / 2 + i * gw / k, 0.3, 1.35, 0.06, 0.1, 2.7)
    for s in (-1, 1):
        mb.box(s * (gw / 2 + 0.3), -0.1, 1.5, 0.6, 0.2, 3.0)               # 袖壁
    mb.box(0, -0.25, fh - 0.15, along - 0.2, 0.3, 0.8)                     # 看板帯
    mb.box(0, -0.42, fh - 0.15, along - 0.5, 0.04, 0.6)
    for i in range(int(along / 0.9)):                                      # 看板の文字(帯の段)
        mb.box(x0 + 0.5 + i * 0.9, -0.45, fh - 0.15, 0.5, 0.02, 0.35)
    mb.box(0, -0.8, 2.75, gw + 0.4, 1.4, 0.06)                             # 庇
    for i in range(int(gw / 0.5)):                                         # 庇のリブ
        mb.box(-gw / 2 + i * 0.5, -0.8, 2.72, 0.03, 1.4, 0.04)
    for s in (-1, 1):
        mb.box_ab((s * gw / 2, -0.02, 2.2), (s * gw / 2, -1.4, 2.72), 0.04)
    # 上の階: 窓、室外機、ときどきベランダ
    ww = rng.choice((1.2, 1.5, 1.8))
    n = max(1, int((along - 1.4) // (ww + 0.7)))
    span = n * ww + (n - 1) * 0.7
    balc = rng.random() < 0.35
    for fl in range(1, floors):
        z = fl * fh + 1.55
        for k in range(n):
            xk = -span / 2 + k * (ww + 0.7) + ww / 2
            window(mb, xk, z, ww, 1.4, rng, grille=(fl == 1 and rng.random() < 0.5))
        if balc and fl % 2 == 0:
            balcony(mb, x0 + 0.2, x1 - 0.2, fl * fh + 0.05, 0.9, rng, partition=False,
                    units=rng.randint(0, 2))
        elif rng.random() < 0.55:
            ac_unit(mb, rng.uniform(x0 + 0.6, x1 - 0.6), -0.25, fl * fh + 0.45, -1)
    import town_kit_more as more
    more.floor_signs(mb, x0, x1, floors, fh, rng)
    more.shop_clutter(mb, x0, x1, rng)
    # 袖看板の塔(片側)
    if floors >= 3:
        sx = x0 + 0.5 if rng.random() < 0.5 else x1 - 0.5
        sign_stack(mb, sx, fh + 0.6, min(h + 0.8, fh + 0.6 + (floors - 1) * fh), rng)
    # 竪樋・メーター
    drain_pipe(mb, x1 - 0.2, -0.08, 0.0, h)
    for k in range(rng.randint(1, 3)):
        meter_box(mb, x0 + 0.6 + k * 0.45, 1.3)
    # 側面(左右): 配管と室外機、ときどき外階段
    for side in (-1, 1):
        xs = side * along / 2
        mb.push(np.array(Matrix.Translation((xs, depth / 2, 0)) @ Matrix.Rotation(-side * math.pi / 2, 4, "Z")))
        # ローカル: 正面 -y が外、x が奥行き方向
        for k in range(rng.randint(2, 5)):
            ac_unit(mb, rng.uniform(-depth / 2 + 0.8, depth / 2 - 0.8), -0.25,
                    rng.uniform(fh, h - 1.0), -1)
        drain_pipe(mb, depth / 2 - 0.3, -0.08, 0.0, h)
        for k in range(rng.randint(1, 3)):                                 # 横走りの配管
            zz = rng.uniform(fh, h - 1)
            mb.cyl_ab((-depth / 2 + 0.3, -0.12, zz), (depth / 2 - 0.3, -0.12, zz), 0.04, 6)
            for i in range(int(depth / 1.2)):
                mb.box(-depth / 2 + 0.6 + i * 1.2, -0.06, zz, 0.05, 0.12, 0.1)
        mb.pop()
    if floors >= 4 and rng.random() < 0.5:
        side = rng.choice((-1, 1))
        fire_escape(mb, side * along / 2, depth * 0.2, depth * 0.8, floors, fh, side)
    # 屋上
    mb.box(0, depth / 2, h + 0.3, along + 0.15, depth + 0.15, 0.6)         # パラペット
    mb.box(0, depth / 2, h + 0.62, along + 0.25, depth + 0.25, 0.06)       # 笠木
    roof_railing(mb, x0 + 0.1, x1 - 0.1, 0.1, depth - 0.1, h + 0.6)
    water_tank(mb, rng.uniform(x0 + 1.5, x1 - 1.5), depth * 0.65, h + 0.6, rng)
    if rng.random() < 0.6 and along > 6:
        billboard(mb, 0, depth * 0.3, h + 0.6, along * 0.8, rng.uniform(1.8, 3.0), rng)
    for _ in range(rng.randint(1, 3)):
        antenna(mb, rng.uniform(x0 + 0.5, x1 - 0.5), rng.uniform(1, depth - 1), h + 0.6,
                rng.uniform(2.0, 4.0), rng)
    if rng.random() < 0.5:
        mb.box(x0 + 1.5, depth - 1.6, h + 1.7, 2.6, 2.4, 2.2)              # 階段室
        mb.box(x0 + 1.5, depth - 1.6, h + 2.85, 2.9, 2.7, 0.1)
    return mb.build(mat)


def apartment(cx, cy, w, d, floors, face, rng, idx):
    """集合住宅: 各階の連続ベランダ(縦桟・仕切り板・室外機・物干し)、掃き出し窓、
    ベランダ裏の竪樋、屋上の塔屋・給水塔・手すり。"""
    floors = floors + rng.choice((3, 4, 5, 6))
    mat, along, depth = facade_matrix(cx, cy, w, d, face)
    mb = MB(f"apt{idx}")
    fh = 2.9
    h = floors * fh + 0.4
    x0, x1 = -along / 2, along / 2
    mb.box(0, depth / 2, h / 2, along, depth, h)
    n = max(2, int(along // 3.6))
    cell = along / n
    for fl in range(floors):
        z0 = fl * fh
        if fl == 0:
            for k in range(n):                                              # 1階: エントランスと窓
                xk = x0 + (k + 0.5) * cell
                window(mb, xk, 1.5, cell * 0.55, 1.4, rng, grille=True)
            mb.box(0, -0.3, 2.7, along * 0.3, 0.6, 0.12)
            continue
        balcony(mb, x0 + 0.1, x1 - 0.1, z0 + 0.05, 1.1, rng, partition=False, units=0)
        for k in range(n):
            xa = x0 + k * cell
            xk = xa + cell * 0.5
            window(mb, xk - cell * 0.12, z0 + 1.1, cell * 0.5, 1.9, rng, sill=False)
            window(mb, xk + cell * 0.32, z0 + 1.7, cell * 0.2, 0.8, rng, sill=False)
            if k > 0:                                                       # 仕切り板
                mb.box(xa, -0.55, z0 + 0.95, 0.04, 1.0, 1.75)
                mb.box(xa, -1.06, z0 + 0.95, 0.06, 0.04, 1.75)
            if rng.random() < 0.75:
                ac_unit(mb, xa + cell * 0.8, -0.8, z0 + 0.35, -1)
            if rng.random() < 0.5:                                          # 物干し竿
                mb.cyl_ab((xa + 0.3, -0.75, z0 + 1.75), (xa + cell - 0.3, -0.75, z0 + 1.75), 0.015, 6)
                for s in (0.3, cell - 0.3):
                    mb.box(xa + s, -0.9, z0 + 1.75, 0.03, 0.3, 0.03)
        for k in range(1, n):                                              # 竪樋
            mb.cyl(x0 + k * cell + 0.12, -0.15, z0 + fh / 2, 0.04, fh, 6)
    # 側面: 窓と外廊下の手すり(奥側の端に)
    for side in (-1, 1):
        xs = side * along / 2
        mb.push(np.array(Matrix.Translation((xs, depth / 2, 0)) @ Matrix.Rotation(-side * math.pi / 2, 4, "Z")))
        for fl in range(1, floors):
            for k in (-1, 1):
                window(mb, k * depth * 0.25, fl * fh + 1.5, 0.8, 1.0, rng, sill=False)
            if rng.random() < 0.4:
                ac_unit(mb, 0, -0.25, fl * fh + 0.5, -1)
        drain_pipe(mb, depth / 2 - 0.3, -0.08, 0, h)
        mb.pop()
    mb.box(0, depth / 2, h + 0.3, along + 0.2, depth + 0.2, 0.6)
    roof_railing(mb, x0 + 0.1, x1 - 0.1, 0.1, depth - 0.1, h + 0.6)
    mb.box(0, depth * 0.6, h + 2.0, 3.2, 3.2, 2.8)                         # 塔屋(エレベーター)
    mb.box(0, depth * 0.6, h + 3.45, 3.5, 3.5, 0.1)
    for i in range(6):
        mb.box(0, depth * 0.6 - 1.62, h + 0.9 + i * 0.35, 2.6, 0.03, 0.05)
    water_tank(mb, along * 0.3, depth * 0.5, h + 0.6, rng)
    cooling_unit(mb, -along * 0.3, depth * 0.4, h + 0.6)
    for _ in range(rng.randint(2, 4)):
        antenna(mb, rng.uniform(x0 + 1, x1 - 1), rng.uniform(1, depth - 1), h + 0.6,
                rng.uniform(1.5, 3.5), rng)
    return mb.build(mat)


def house(cx, cy, w, d, face, rng, idx):
    """木造の家: 瓦屋根(瓦の段 25cm おき・棟・破風)、軒樋と竪樋、格子の窓、
    玄関庇、板塀と門柱、室外機、メーター。"""
    mat, along, depth = facade_matrix(cx, cy, w, d, face)
    mb = MB(f"house{idx}")
    bw, bd = along * 0.78, depth * 0.72
    by0 = depth - bd - 0.3                                                 # 奥に寄せる
    h = 5.6
    mb.box(0, by0 + bd / 2, h / 2, bw, bd, h)
    mb.box(0, by0 - 0.04, 2.85, bw + 0.1, 0.08, 0.12)                      # 2階の胴差し
    # 屋根(棟は x 方向)
    ov = 0.5
    rise = bd * 0.35
    rx0, rx1 = -bw / 2 - ov, bw / 2 + ov
    ry0, ry1 = by0 - ov, by0 + bd + ov
    mb.prism(rx0, rx1, ry0, ry1, h, h + rise)
    ym = (ry0 + ry1) / 2
    slope = math.atan2(rise, (ry1 - ry0) / 2)
    run = (ry1 - ry0) / 2
    k = int(run / 0.25)
    for i in range(1, k):                                                  # 瓦の段
        t = i / k
        for s in (-1, 1):
            yy = ym + s * run * (1 - t)
            zz = h + rise * t + 0.03
            mb.box((rx0 + rx1) / 2, yy, zz, rx1 - rx0, 0.05, 0.05)
    mb.box((rx0 + rx1) / 2, ym, h + rise + 0.08, rx1 - rx0 + 0.1, 0.25, 0.18)   # 棟
    for xs in (rx0, rx1):                                                  # 破風
        for s in (-1, 1):
            mb.box_ab((xs, ym + s * run, h), (xs, ym, h + rise), 0.08, 0.25)
    for yy in (ry0, ry1):                                                  # 軒樋
        mb.cyl_ab((rx0, yy, h - 0.05), (rx1, yy, h - 0.05), 0.06, 8)
    drain_pipe(mb, rx1 - 0.1, ry0, 0.0, h - 0.05)
    # 正面の窓(格子)と玄関
    for fl in (0, 1):
        for xk in (-bw * 0.28, bw * 0.28):
            mb.push(np.array(Matrix.Translation((0, by0, 0))))
            window(mb, xk, 1.3 + fl * 2.8, 1.5, 1.1, rng, grille=True)
            mb.pop()
    mb.box(0, by0 - 0.02, 1.05, 0.95, 0.06, 2.1)                           # 玄関戸
    for i in range(6):
        mb.box(-0.4 + i * 0.16, by0 - 0.06, 1.05, 0.03, 0.02, 2.0)
    mb.box(0, by0 - 0.55, 2.4, 1.8, 1.1, 0.08)                             # 玄関庇
    for s in (-1, 1):
        mb.box_ab((s * 0.8, by0 - 0.02, 2.0), (s * 0.8, by0 - 1.0, 2.38), 0.04)
    ac_unit(mb, bw * 0.4, by0 - 0.3, 0.4, -1)
    # 板塀と門柱(通り側、ローカル y=0)
    gate = 1.2
    for s in (-1, 1):
        xa, xb = s * gate / 2, s * along / 2
        L = abs(xb - xa)
        mb.box((xa + xb) / 2, 0.1, 0.9, L, 0.06, 1.8)
        for i in range(int(L / 0.12)):
            mb.box(xa + s * (i + 0.5) * 0.12, 0.05, 0.9, 0.02, 0.03, 1.8)
        mb.box((xa + xb) / 2, 0.05, 1.82, L, 0.1, 0.06)
        mb.box(s * gate / 2, 0.1, 1.0, 0.3, 0.3, 2.0)
    mb.box(-gate / 2 - 0.4, 0.0, 1.3, 0.3, 0.1, 0.4)                       # ポスト
    return mb.build(mat)


def konbini(cx, cy, w, d, face, rng, idx):
    """コンビニ: ガラス面(方立 1.2m)、看板帯、庇と柱、ATM 看板、屋上機器、室外機の列。"""
    mat, along, depth = facade_matrix(cx, cy, w, d, face)
    mb = MB(f"konbini{idx}")
    h = 4.4
    mb.box(0, depth / 2, h / 2, along, depth, h)
    gw = along - 1.2
    mb.box(0, 0.25, 1.5, gw, 0.04, 2.8)
    k = int(gw / 1.2)
    for i in range(k + 1):
        mb.box(-gw / 2 + i * gw / k, 0.2, 1.5, 0.08, 0.1, 2.8)
    mb.box(0, 0.2, 2.2, gw, 0.08, 0.06)
    mb.box(0, -0.25, h - 0.55, along + 0.4, 0.5, 1.0)                      # 看板帯
    for i in range(3):
        mb.box(0, -0.52, h - 0.85 + i * 0.3, along, 0.03, 0.12)
    mb.box(0, -1.3, 3.0, gw + 0.6, 2.6, 0.1)                               # 庇
    for s in (-1, 1):
        mb.cyl(s * (gw / 2 - 0.2), -2.4, 1.5, 0.08, 3.0, 8)
    for i in range(int(gw / 0.6)):
        mb.box(-gw / 2 + i * 0.6, -1.3, 2.94, 0.04, 2.6, 0.06)
    for side in (-1, 1):
        xs = side * along / 2
        mb.push(np.array(Matrix.Translation((xs, depth / 2, 0)) @ Matrix.Rotation(-side * math.pi / 2, 4, "Z")))
        for i in range(4):
            ac_unit(mb, -depth / 2 + 1.5 + i * 1.1, -0.3, 0.45, -1)
        mb.box(0, -0.2, h - 0.55, depth + 0.4, 0.4, 1.0)
        mb.pop()
    mb.box(0, depth / 2, h + 0.2, along + 0.2, depth + 0.2, 0.4)
    cooling_unit(mb, along * 0.2, depth * 0.6, h + 0.4)
    cooling_unit(mb, -along * 0.2, depth * 0.6, h + 0.4)
    return mb.build(mat)


def parking(cx, cy, w, d, face, rng, idx):
    """月極駐車場: 金網フェンス(柱・横桟・縦の網目)、車止め、看板。"""
    mat, along, depth = facade_matrix(cx, cy, w, d, face)
    mb = MB(f"parking{idx}")
    x0, x1 = -along / 2, along / 2
    for (a, b) in (((x0, 0.0), (x0, depth)), ((x0, depth), (x1, depth)), ((x1, depth), (x1, 0.0))):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(L / 2.0))
        for i in range(k + 1):
            t = i / k
            mb.cyl(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 0.9, 0.035, 1.8, 6)
        for z in (0.1, 0.9, 1.8):
            mb.cyl_ab((a[0], a[1], z), (b[0], b[1], z), 0.02, 4)
        m = int(L / 0.15)
        for i in range(m):                                                 # 網目(縦)
            t = (i + 0.5) / m
            mb.box(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 0.95, 0.01, 0.01, 1.7)
    slots = int(along // 2.6)
    for i in range(slots):
        xk = x0 + (i + 0.5) * along / slots
        mb.box(xk, depth * 0.85, 0.06, 0.6, 0.15, 0.12)
    mb.box(x0 + 0.5, 0.2, 1.6, 0.05, 0.05, 3.2)                            # 看板
    mb.box(x0 + 0.5, 0.15, 2.8, 1.2, 0.06, 0.8)
    return mb.build(mat)


# ---------------------------------------------------------------- 街路

def street(rng, ROAD, WALK, CURB, CROSS, XW, obstacles):
    """車道の縁の歩道・縁石、電柱(腕木・碍子・変圧器・足場ボルト)と電線の束、
    信号、街灯、標識、カーブミラー、ガードレール、自販機、自転車、電気の箱、
    遠景のビル、そして横町をまたぐ高架道路。"""
    mb = MB("street")
    ylo, yhi = -70.0, 140.0
    # 歩道(縁石は歩道の箱そのもの。重ねると Z ファイトした)
    for sx in (-1, 1):
        segs = [(ylo, CROSS[0] - XW), (CROSS[0] + XW, CROSS[1] - XW), (CROSS[1] + XW, yhi)]
        for y0, y1 in segs:
            mb.box(sx * (ROAD + WALK / 2), (y0 + y1) / 2, 0.075, WALK, y1 - y0, 0.15)
            k = int((y1 - y0) / 0.9)                                        # 舗装の目地
            for i in range(1, k):
                mb.box(sx * (ROAD + WALK / 2), y0 + i * (y1 - y0) / k, 0.152, WALK - 0.1, 0.02, 0.006)
    for cy in CROSS:
        for sy in (-1, 1):
            for x0, x1 in ((-70.0, -CURB), (CURB, 70.0)):
                mb.box((x0 + x1) / 2, cy + sy * (XW + WALK / 2), 0.075, x1 - x0, WALK, 0.15)

    # 電柱と電線の束
    poles = []
    for y in range(int(ylo) + 6, int(yhi), 22):
        if any(abs(y - c) < XW + 3 for c in CROSS):
            y += 4
        px = ROAD + 0.9
        obstacles.append((px, y, 0.4))
        mb.cyl(px, y, 5.5, 0.17, 11.0, 12, r2=0.12)
        for zz in (9.6, 10.4, 8.8):                                          # 腕木
            mb.box(px, y, zz, 0.12, 2.6, 0.12)
            for s in (-1, 0, 1):                                             # 碍子
                mb.cyl(px, y + s * 1.1, zz + 0.12, 0.05, 0.14, 8)
                mb.cyl(px, y + s * 1.1, zz + 0.2, 0.07, 0.03, 8)
            mb.box_ab((px, y - 1.0, zz), (px, y, zz - 0.6), 0.05)            # 腕木の支え
            mb.box_ab((px, y + 1.0, zz), (px, y, zz - 0.6), 0.05)
        if rng.random() < 0.6:                                              # 変圧器(2つ)
            for s in (-1, 1):
                mb.cyl(px + 0.45, y + s * 0.35, 7.6, 0.28, 0.9, 14)
                mb.cyl(px + 0.45, y + s * 0.35, 8.1, 0.3, 0.06, 14)
            mb.box(px + 0.25, y, 7.2, 0.4, 1.2, 0.08)
            mb.box(px + 0.25, y, 8.0, 0.4, 1.2, 0.08)
        for i in range(12):                                                  # 足場ボルト
            zz = 2.0 + i * 0.45
            s = (-1) ** i
            mb.box(px, y + s * 0.2, zz, 0.03, 0.25, 0.03)
        mb.box(px - 0.18, y, 2.6, 0.02, 0.3, 0.9)                            # 巻き看板
        poles.append((px, y))
    for (x0, y0), (x1, y1) in zip(poles, poles[1:]):                          # 電線(10本)
        for dy_, z in ((-1.1, 9.72), (0.0, 9.72), (1.1, 9.72), (-1.1, 10.52), (0.0, 10.52),
                       (1.1, 10.52), (-1.1, 8.92), (0.0, 8.92), (1.1, 8.92), (0.3, 7.0)):
            sag = 0.35 + 0.1 * rng.random()
            prev = None
            for i in range(9):
                t = i / 8
                p = (x0 + (x1 - x0) * t, y0 + dy_ + (y1 - y0) * t,
                     z - sag * 4 * t * (1 - t))
                if prev is not None:
                    mb.cyl_ab(prev, p, 0.014, 4)
                prev = p
    for k, (px, py) in enumerate(poles):                                     # 引き込み線
        for j in range(rng.randint(2, 4)):
            tx = CURB + 0.1
            ty = py + rng.uniform(-8, 8)
            tz = rng.uniform(5.5, 8.5)
            mb.cyl_ab((px, py, 8.9), (tx, ty, tz), 0.01, 4)
        if k % 2 == 0:                                                       # 通りをまたぐ線
            for dz in (0.0, 0.3, 0.6):
                mb.cyl_ab((px, py, 9.7 - dz), (-(ROAD + 1.0), py + 3.0, 8.4 - dz), 0.012, 4)

    # 街灯(反対側)
    for y in range(int(ylo) + 14, int(yhi), 26):
        if any(abs(y - c) < XW + 3 for c in CROSS):
            continue
        lx = -(ROAD + 0.8)
        obstacles.append((lx, y, 0.25))
        mb.cyl(lx, y, 3.2, 0.09, 6.4, 10, r2=0.06)
        mb.box_ab((lx, y, 6.2), (lx + 1.7, y, 6.5), 0.06)
        mb.box(lx + 1.8, y, 6.45, 0.6, 0.3, 0.15)
        mb.box(lx + 1.8, y, 6.35, 0.5, 0.22, 0.05)
        mb.box(lx - 0.12, y, 2.5, 0.12, 0.25, 0.4)                           # 点検口

    # 信号(交差点の各角): 柱、腕、灯器(箱+3灯+ひさし)、歩行者用、押しボタン
    for cy in CROSS:
        for sx, sy in ((1, -1), (-1, 1), (1, 1), (-1, -1)):
            px, py = sx * (ROAD + 0.7), cy + sy * (XW + 0.7)
            obstacles.append((px, py, 0.3))
            mb.cyl(px, py, 3.0, 0.1, 6.0, 10)
            ax = px - sx * 3.4
            arm_z = 5.7
            mb.box_ab((px, py, arm_z), (ax, py, arm_z), 0.1)
            mb.box_ab((px, py, arm_z - 0.8), (px - sx * 1.5, py, arm_z), 0.05)   # 腕の支え
            box_h, box_d = 0.42, 0.35
            box_z = arm_z - 0.05 - box_h / 2
            bx = ax + sx * 0.6
            mb.box(bx, py, box_z, 1.25, box_d, box_h)
            for k in range(3):
                lx_ = ax + sx * (0.2 + 0.42 * k)
                fy = py - sy * (box_d / 2 + 0.01)
                mb.cyl_ab((lx_, fy, box_z), (lx_, fy - sy * 0.04, box_z), 0.13, 12)
                mb.ring(lx_, fy - sy * 0.05, box_z, 0.16, 0.03, 0.02, 12, "y")
                mb.box(lx_, fy - sy * 0.2, box_z + 0.15, 0.3, 0.35, 0.02)   # ひさし
            mb.box(bx, py - sy * 0.1, box_z + box_h / 2 + 0.2, 1.1, 0.05, 0.3)   # 交差点名
            mb.box(px, py - sy * 0.25, 2.6, 0.3, 0.2, 0.7)                   # 歩行者用
            mb.box(px, py - sy * 0.37, 2.75, 0.22, 0.02, 0.22)
            mb.box(px, py - sy * 0.37, 2.45, 0.22, 0.02, 0.22)
            mb.box(px, py + sy * 0.15, 1.1, 0.18, 0.1, 0.3)                  # 押しボタン
        # ガードレール(交差点付近): 柱と2段のビーム
        for sx in (-1, 1):
            for sy in (-1, 1):
                y0 = cy + sy * (XW + 2.0)
                y1 = cy + sy * (XW + 14.0)
                for k in range(9):
                    yy = y0 + (y1 - y0) * k / 8
                    mb.cyl(sx * (ROAD + 0.3), yy, 0.45, 0.05, 0.9, 8)
                for zz in (0.72, 0.5):
                    mb.box(sx * (ROAD + 0.3) + sx * 0.08, (y0 + y1) / 2, zz, 0.04, abs(y1 - y0), 0.16)

    # 標識・カーブミラー
    for (x, y, kind) in ((-(ROAD + 0.5), -18.0, "disc"), (ROAD + 0.5, 20.0, "tri"),
                         (-(ROAD + 0.5), 44.0, "rect"), (ROAD + 0.5, 84.0, "disc"),
                         (-(ROAD + 0.5), 104.0, "mirror"), (ROAD + 0.5, -40.0, "mirror")):
        obstacles.append((x, y, 0.2))
        mb.cyl(x, y, 1.5, 0.04, 3.0, 8)
        if kind == "disc":
            mb.cyl_ab((x, y, 2.7), (x, y - 0.03, 2.7), 0.3, 16)
            mb.ring(x, y - 0.04, 2.7, 0.3, 0.04, 0.01, 16, "y")
        elif kind == "tri":
            mb.box(x, y, 2.75, 0.03, 0.02, 0.02)
            for a in (90, 210, 330):
                r1, r2 = math.radians(a), math.radians(a + 120)
                mb.box_ab((x + 0.35 * math.cos(r1), y - 0.02, 2.7 + 0.35 * math.sin(r1)),
                          (x + 0.35 * math.cos(r2), y - 0.02, 2.7 + 0.35 * math.sin(r2)), 0.05)
        elif kind == "rect":
            mb.box(x, y - 0.02, 2.6, 0.6, 0.03, 0.8)
            mb.box(x, y - 0.04, 2.6, 0.5, 0.01, 0.1)
        else:
            mb.box_ab((x, y, 2.9), (x, y - 0.4, 3.0), 0.05)
            mb.cyl_ab((x, y - 0.5, 3.0), (x, y - 0.56, 3.0), 0.4, 20)
            mb.ring(x, y - 0.58, 3.0, 0.42, 0.05, 0.03, 20, "y")

    # 自販機(ボタンの列・取り出し口・ロゴ帯)
    for y in (-30.0, 22.0, 46.0, 96.0):
        sx = rng.choice((-1, 1))
        x = sx * (ROAD + 2.9)
        obstacles.append((x, y, 0.8))
        for j in (-0.5, 0.5):                                               # 2台並び
            yy = y + j * 1.05
            mb.box(x, yy, 0.92, 0.8, 1.0, 1.84)
            fx = x - sx * 0.41
            mb.box(fx, yy, 1.35, 0.02, 0.85, 0.7)                          # 見本の窓
            for r_ in range(3):
                for c_ in range(6):
                    mb.box(fx - sx * 0.02, yy - 0.35 + c_ * 0.14, 1.08 + r_ * 0.23, 0.02, 0.1, 0.12)
                    mb.box(fx - sx * 0.03, yy - 0.35 + c_ * 0.14, 1.0 + r_ * 0.23, 0.02, 0.06, 0.02)
            mb.box(fx - sx * 0.01, yy, 0.25, 0.03, 0.6, 0.2)                # 取り出し口
            mb.box(fx - sx * 0.01, yy + 0.3, 0.75, 0.03, 0.12, 0.2)         # 投入口
    # 自転車(輪・スポーク・フレーム・ハンドル・サドル)の列
    for (bx0, by0, n) in ((-(ROAD + 2.7), 30.0, 4), (ROAD + 2.7, 106.0, 5)):
        for i in range(n):
            by = by0 + i * 0.7
            obstacles.append((bx0, by, 0.9))
            for wx in (-0.52, 0.52):
                mb.ring(bx0 + wx, by, 0.34, 0.33, 0.04, 0.03, 18, "y")
                mb.cyl(bx0 + wx, by, 0.34, 0.04, 0.04, 8)
                for a in range(0, 180, 30):
                    r = math.radians(a)
                    mb.box_ab((bx0 + wx - 0.29 * math.cos(r), by, 0.34 - 0.29 * math.sin(r)),
                              (bx0 + wx + 0.29 * math.cos(r), by, 0.34 + 0.29 * math.sin(r)), 0.006)
            pts = [(bx0 - 0.52, by, 0.34), (bx0 - 0.05, by, 0.36), (bx0 + 0.35, by, 0.8),
                   (bx0 - 0.15, by, 0.85), (bx0 - 0.05, by, 0.36)]
            for a, b in zip(pts, pts[1:]):
                mb.cyl_ab(a, b, 0.018, 6)
            mb.cyl_ab((bx0 + 0.52, by, 0.34), (bx0 + 0.38, by, 0.95), 0.018, 6)
            mb.box(bx0 + 0.38, by, 0.98, 0.04, 0.5, 0.03)                    # ハンドル
            mb.box(bx0 - 0.2, by, 0.92, 0.22, 0.1, 0.05)                     # サドル
            mb.box(bx0 + 0.5, by, 0.75, 0.25, 0.25, 0.15)                    # かご

    # 電気の箱・消火栓・ポスト
    for (x, y) in ((ROAD + 1.5, 12.0), (-(ROAD + 1.5), 78.0), (ROAD + 1.5, -52.0)):
        obstacles.append((x, y, 0.6))
        mb.box(x, y, 0.7, 0.6, 1.0, 1.4)
        mb.box(x, y, 1.42, 0.7, 1.1, 0.05)
        for i in range(4):
            mb.box(x - 0.31, y, 0.3 + i * 0.3, 0.01, 0.8, 0.02)
    obstacles.append((ROAD + 1.2, 30.0, 0.35))
    mb.cyl(ROAD + 1.2, 30.0, 0.55, 0.22, 1.1, 14)
    mb.box(ROAD + 1.2, 30.0, 1.15, 0.5, 0.5, 0.1)
    mb.box(ROAD + 1.2 - 0.23, 30.0, 0.85, 0.02, 0.25, 0.04)
    # 植樹枡(木は assets 側)
    for y in range(-50, 132, 18):
        if any(abs(y - c) < XW + 6 for c in CROSS):
            continue
        for sx in (-1, 1):
            x = sx * (ROAD + 1.9)
            obstacles.append((x, y, 1.3))
            mb.box(x, y, 0.19, 1.6, 1.6, 0.08)
            mb.box(x, y, 0.1, 1.3, 1.3, 0.12)
            for i in range(5):                                               # 根元の格子
                mb.box(x - 0.5 + i * 0.25, y, 0.24, 0.03, 1.2, 0.02)

    # 遠景のビル群(北): 窓の段と屋上の機器
    for k in range(12):
        bx = rng.uniform(-80, 80)
        by = rng.uniform(190, 330)
        bw, bd, bh = rng.uniform(16, 30), rng.uniform(16, 30), rng.uniform(30, 90)
        mb.box(bx, by, bh / 2, bw, bd, bh)
        mb.box(bx, by, bh + 0.4, bw + 0.6, bd + 0.6, 0.8)
        for fl in range(2, int(bh // 3.4)):
            mb.box(bx, by - bd / 2 - 0.06, fl * 3.4, bw - 2.0, 0.12, 1.5)
        for i in range(int(bw / 3)):
            mb.box(bx - bw / 2 + 1.5 + i * 3, by - bd / 2 - 0.1, bh / 2, 0.15, 0.1, bh - 4)
        mb.box(bx, by, bh + 2.0, bw * 0.4, bd * 0.4, 3.0)
        antenna(mb, bx + bw * 0.3, by, bh + 0.8, rng.uniform(4, 9), rng)

    import town_kit_more as more
    more.cross_cables(mb, poles, ROAD, CURB, rng)
    more.pedestrian_bridge(mb, 30.0, ROAD, WALK, obstacles)
    elevated_expressway(mb, CROSS[1], ROAD, rng, obstacles)
    return mb.build()


def elevated_expressway(mb, yc, ROAD, rng, obstacles):
    """横町(y=yc)の上を渡る高架道路: 床版、I 桁5本、横桁、支承、T 型の橋脚、
    高欄、遮音壁(パネルと柱)、照明柱、床版下の排水管。"""
    z0 = 11.0                     # 床版の下面
    W = 12.0                      # 幅
    xa, xb = -95.0, 95.0
    L = xb - xa
    mb.box(0, yc, z0 + 0.3, L, W, 0.6)                                     # 床版
    for gy in (-4.8, -2.4, 0.0, 2.4, 4.8):                                 # I 桁
        y = yc + gy
        mb.box(0, y, z0 - 0.75, L, 0.12, 1.3)                              # ウェブ
        mb.box(0, y, z0 - 1.42, L, 0.5, 0.06)                              # 下フランジ
        mb.box(0, y, z0 - 0.08, L, 0.45, 0.06)
        for i in range(int(L / 1.5)):                                       # 補剛材
            mb.box(xa + i * 1.5, y, z0 - 0.75, 0.03, 0.4, 1.25)
    for i in range(int(L / 5.0) + 1):                                       # 横桁
        x = xa + i * 5.0
        mb.box(x, yc, z0 - 0.7, 0.1, W - 1.2, 0.9)
        mb.box_ab((x, yc - 4.8, z0 - 1.4), (x, yc - 2.4, z0 - 0.1), 0.06)
        mb.box_ab((x, yc + 4.8, z0 - 1.4), (x, yc + 2.4, z0 - 0.1), 0.06)
    for s in (-1, 1):                                                       # 高欄と遮音壁
        ye = yc + s * (W / 2 - 0.15)
        mb.box(0, ye, z0 + 1.1, L, 0.3, 1.0)
        mb.box(0, ye - s * 0.2, z0 + 1.6, L, 0.1, 0.05)
        for i in range(int(L / 2.0) + 1):
            x = xa + i * 2.0
            mb.box(x, ye, z0 + 2.9, 0.12, 0.18, 2.6)                       # 支柱
        mb.box(0, ye + s * 0.02, z0 + 2.9, L, 0.06, 2.4)                   # パネル
        for zz in (z0 + 1.7, z0 + 2.5, z0 + 3.3, z0 + 4.1):
            mb.box(0, ye + s * 0.07, zz, L, 0.04, 0.06)                    # パネルの継ぎ目
        mb.box(0, ye, z0 + 4.15, L, 0.4, 0.1)                              # 笠木
        mb.cyl_ab((xa, ye - s * 0.4, z0 - 0.2), (xb, ye - s * 0.4, z0 - 0.2), 0.1, 8)   # 排水管
        for i in range(int(L / 30.0) + 1):                                 # 照明柱
            x = xa + 15 + i * 30.0
            mb.cyl(x, ye - s * 0.3, z0 + 5.0, 0.1, 8.0, 10)
            mb.box_ab((x, ye - s * 0.3, z0 + 8.8), (x, ye - s * 2.8, z0 + 9.3), 0.07)
            mb.box(x, ye - s * 2.9, z0 + 9.25, 0.35, 0.8, 0.18)
        for i in range(int(L / 2.0)):                                       # 床版の端の目地
            mb.box(xa + 1 + i * 2.0, ye + s * 0.16, z0 + 0.3, 0.02, 0.02, 0.5)
    for x in (-54.0, -34.0, -16.0, 16.0, 34.0, 54.0):                       # T 型の橋脚
        obstacles.append((x, yc, 1.2))
        mb.box(x, yc, (z0 - 1.5) / 2, 1.8, 1.8, z0 - 1.5)
        for s in (-1, 1):                                                   # 柱の面取り(縦の目地)
            mb.box(x + s * 0.91, yc, (z0 - 1.5) / 2, 0.02, 1.2, z0 - 1.5)
            mb.box(x, yc + s * 0.91, (z0 - 1.5) / 2, 1.2, 0.02, z0 - 1.5)
        mb.box(x, yc, z0 - 2.0, 2.2, W - 0.6, 1.0)                         # はり
        mb.box_ab((x, yc - 0.9, z0 - 4.0), (x, yc - (W / 2 - 0.5), z0 - 2.5), 0.9, 0.6)
        mb.box_ab((x, yc + 0.9, z0 - 4.0), (x, yc + (W / 2 - 0.5), z0 - 2.5), 0.9, 0.6)
        for gy in (-4.8, -2.4, 0.0, 2.4, 4.8):                             # 支承
            mb.box(x, yc + gy, z0 - 1.46, 0.6, 0.6, 0.1)
        for zz in (3.0, 6.0):                                               # 点検のはしご
            mb.box(x - 0.95, yc, zz, 0.03, 0.4, 0.03)
        for i in range(20):
            mb.box(x - 0.95, yc, 0.5 + i * 0.4, 0.03, 0.35, 0.03)
