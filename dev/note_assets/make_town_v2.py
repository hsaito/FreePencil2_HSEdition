"""日本の街路らしい町を組む(v2)。線画で「町」に見える密度まで作り込む。

建物は種類ごとに手続きで作る(部品を1棟に結合。STEP1 は棟ごとに塗り、
窓などのルースパーツは近接隣接で色が分かれる):
    shophouse   1階が店(ガラス面・看板・庇・シャッター)、上階に窓と
                ベランダ(手すり)、雨樋、室外機、屋上に給水タンク
    apartment   外廊下型。各階に連続ベランダと手すり板、端に外階段、屋上タンク
    house       2階建て切妻屋根、軒、塀と門、カーポート
    konbini     平屋の大きなガラス面と看板帯、前に駐車場
    parking     フェンス付き駐車場と車
街路: 車道・歩道・縁石・ガードレール・横断歩道・停止線・マンホール、
      電柱と電線、信号機、街灯、自販機、バス停、街路樹(植樹枡)、
      車・人(アセットのリンク複製)

  blender -b --factory-startup --python make_town_v2.py -- \
      [--out out/town_v2] [--style BACKGROUND] [--seed 5]
"""
from __future__ import annotations

import math
import random
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "town_v2"))).resolve()
STYLE = arg("--style", "BACKGROUND")
SEED = int(arg("--seed", "5"))
SKIP = set(arg("--skip", "").split(","))    # 調査用: people / cars / trees を外す

sys.argv = ["blender", "--", "--out", str(OUT), "--res", "1920", "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_town_demo as td       # noqa: E402
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import bmesh                      # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()

ROAD = 5.5           # 車道の半幅(2車線)
WALK = 3.5           # 歩道
CURB = ROAD + WALK   # 街区の始まり
CROSS = (0.0, 64.0)  # 横町の中心 y
XW = 5.0             # 横町の半幅


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# ---------------------------------------------------------------- 部品(1棟にまとめる前の箱)

class Parts:
    """1つのメッシュに結合する部品の集まり。"""

    def __init__(self, name):
        self.name = name
        self.objs = []

    def box(self, cx, cy, cz, sx, sy, sz, rz=0.0):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, cz))
        o = bpy.context.object
        o.scale = (sx, sy, sz)
        o.rotation_euler = (0.0, 0.0, rz)
        self.objs.append(o)
        return o

    def cyl(self, cx, cy, cz, r, h, verts=10, rot=(0.0, 0.0, 0.0)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h,
                                            location=(cx, cy, cz), rotation=rot)
        o = bpy.context.object
        self.objs.append(o)
        return o

    def bar(self, a, b, r=0.02, verts=6):
        """2点を結ぶ細い円柱(電線・手すり)。"""
        a, b = Vector(a), Vector(b)
        d = b - a
        mid = (a + b) / 2
        rot = d.to_track_quat("Z", "Y").to_euler()
        return self.cyl(mid.x, mid.y, mid.z, r, d.length, verts, rot)

    def prism(self, cx, cy, z0, w, d, h_eave, h_ridge, along="x"):
        """切妻屋根。along は棟の向き。"""
        me = bpy.data.meshes.new("roof")
        bm = bmesh.new()
        hw, hd = w / 2, d / 2
        if along == "x":
            v = [bm.verts.new(p) for p in (
                (-hw, -hd, z0), (hw, -hd, z0), (hw, hd, z0), (-hw, hd, z0),
                (-hw, 0, z0 + (h_ridge - h_eave)), (hw, 0, z0 + (h_ridge - h_eave)))]
            bm.faces.new((v[0], v[1], v[5], v[4]))
            bm.faces.new((v[3], v[4], v[5], v[2]))
            bm.faces.new((v[0], v[4], v[3]))
            bm.faces.new((v[1], v[2], v[5]))
        else:
            v = [bm.verts.new(p) for p in (
                (-hw, -hd, z0), (hw, -hd, z0), (hw, hd, z0), (-hw, hd, z0),
                (0, -hd, z0 + (h_ridge - h_eave)), (0, hd, z0 + (h_ridge - h_eave)))]
            bm.faces.new((v[0], v[4], v[5], v[3]))
            bm.faces.new((v[1], v[2], v[5], v[4]))
            bm.faces.new((v[0], v[1], v[4]))
            bm.faces.new((v[3], v[5], v[2]))
        bm.faces.new((v[0], v[3], v[2], v[1]))
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new("roof", me)
        bpy.context.scene.collection.objects.link(o)
        o.location = (cx, cy, 0.0)
        self.objs.append(o)
        return o

    def join(self):
        if not self.objs:
            return None
        bpy.ops.object.select_all(action="DESELECT")
        for o in self.objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = self.objs[0]
        bpy.ops.object.join()
        o = bpy.context.object
        o.name = self.name
        # 結合後にスケールを焼く(角度判定はメッシュ座標で行う)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        return o


def facing(face):
    """正面の向き -> (法線 nx, ny)。"""
    return {"-x": (-1, 0), "+x": (1, 0), "-y": (0, -1), "+y": (0, 1)}[face]


def wall_point(cx, cy, w, d, face, t, out):
    """正面の壁の上で、横位置 t(中心から)、壁から out だけ外の点。"""
    nx, ny = facing(face)
    if face in ("-x", "+x"):
        return (cx + nx * (w / 2 + out), cy + t)
    return (cx + t, cy + ny * (d / 2 + out))


def side_dims(w, d, face):
    """正面の幅(along)と奥行き。"""
    return (d, w) if face in ("-x", "+x") else (w, d)


def window(P, cx, cy, w, d, face, t, z, ww, wh, frame=0.08, sill=True):
    nx, ny = facing(face)
    x, y = wall_point(cx, cy, w, d, face, t, 0.0)
    if face in ("-x", "+x"):
        P.box(x + nx * 0.05, y, z, 0.10, ww + frame * 2, wh + frame * 2)        # 枠
        P.box(x - nx * 0.06, y, z, 0.06, ww, wh)                                 # ガラス(奥)
        if sill:
            P.box(x + nx * 0.12, y, z - wh / 2 - frame - 0.04, 0.24, ww + frame * 2 + 0.2, 0.08)
    else:
        P.box(x, y + ny * 0.05, z, ww + frame * 2, 0.10, wh + frame * 2)
        P.box(x, y - ny * 0.06, z, ww, 0.06, wh)
        if sill:
            P.box(x, y + ny * 0.12, z - wh / 2 - frame - 0.04, ww + frame * 2 + 0.2, 0.24, 0.08)


def railing(P, x0, y0, x1, y1, z, h=1.1, posts=None):
    """手すり: 上下の横桟 + 縦桟。"""
    a, b = Vector((x0, y0, z)), Vector((x1, y1, z))
    L = (b - a).length
    P.bar((x0, y0, z + h), (x1, y1, z + h), 0.03)
    P.bar((x0, y0, z + 0.12), (x1, y1, z + 0.12), 0.02)
    n = posts or max(2, int(L / 1.2) + 1)
    for k in range(n):
        p = a.lerp(b, k / (n - 1)) if n > 1 else a
        P.bar((p.x, p.y, z), (p.x, p.y, z + h), 0.025)


def ac_unit(P, cx, cy, w, d, face, t, z):
    nx, ny = facing(face)
    x, y = wall_point(cx, cy, w, d, face, t, 0.22)
    if face in ("-x", "+x"):
        P.box(x, y, z, 0.32, 0.85, 0.58)
        P.box(x + nx * 0.17, y, z, 0.02, 0.6, 0.4)
    else:
        P.box(x, y, z, 0.85, 0.32, 0.58)
        P.box(x, y + ny * 0.17, z, 0.6, 0.02, 0.4)


# ---------------------------------------------------------------- 建物

def shophouse(cx, cy, w, d, floors, face, rng, idx):
    P = Parts(f"shop{idx}")
    fh = 3.3
    h = floors * fh + 0.5
    nx, ny = facing(face)
    along, depth = side_dims(w, d, face)
    # 躯体(1階の正面はガラス面を奥に引っ込める)
    P.box(cx, cy, h / 2, w, d, h)
    x, y = wall_point(cx, cy, w, d, face, 0.0, 0.0)
    # 1階: ガラス面(奥へ 0.5)、左右の柱、上の看板、庇
    glass_w = along - 1.6
    if face in ("-x", "+x"):
        P.box(x - nx * 0.5, y, 1.55, 0.08, glass_w, 2.9)
        for s in (-1, 1):
            P.box(x - nx * 0.25, y + s * (glass_w / 2 + 0.3), 1.55, 0.6, 0.5, 3.1)
        P.box(x + nx * 0.12, y, fh + 0.05, 0.25, along - 0.4, 0.9)           # 看板
        P.box(x + nx * 0.85, y, 2.95, 1.7, glass_w + 0.6, 0.08)                # 庇
        for k in range(1, int(glass_w // 1.1)):
            P.box(x - nx * 0.5, y - glass_w / 2 + k * 1.1, 1.55, 0.12, 0.08, 2.9)   # 方立
        P.box(x - nx * 0.5, y, 0.12, 0.2, glass_w, 0.24)                       # 腰
    else:
        P.box(x, y - ny * 0.5, 1.55, glass_w, 0.08, 2.9)
        for s in (-1, 1):
            P.box(x + s * (glass_w / 2 + 0.3), y - ny * 0.25, 1.55, 0.5, 0.6, 3.1)
        P.box(x, y + ny * 0.12, fh + 0.05, along - 0.4, 0.25, 0.9)
        P.box(x, y + ny * 0.85, 2.95, glass_w + 0.6, 1.7, 0.08)
        for k in range(1, int(glass_w // 1.1)):
            P.box(x - glass_w / 2 + k * 1.1, y - ny * 0.5, 1.55, 0.08, 0.12, 2.9)
        P.box(x, y - ny * 0.5, 0.12, glass_w, 0.2, 0.24)
    # 上階: 窓(枠+ガラス+水切り)、ときどきベランダ
    ww = rng.choice((1.2, 1.5, 1.8))
    n = max(1, int((along - 1.2) // (ww + 0.9)))
    span = n * ww + (n - 1) * 0.9
    balcony_floor = rng.choice((None, 1, 2)) if floors >= 2 else None
    for fl in range(1, floors):
        z = fl * fh + 1.6
        for k in range(n):
            t = -span / 2 + k * (ww + 0.9) + ww / 2
            window(P, cx, cy, w, d, face, t, z, ww, 1.4)
        if balcony_floor is not None and fl == balcony_floor:
            bx, by = wall_point(cx, cy, w, d, face, 0.0, 0.7)
            if face in ("-x", "+x"):
                P.box(bx, by, fl * fh + 0.08, 1.4, along - 0.6, 0.16)
                railing(P, bx + nx * 0.6, by - (along - 0.6) / 2, bx + nx * 0.6, by + (along - 0.6) / 2, fl * fh + 0.16)
            else:
                P.box(bx, by, fl * fh + 0.08, along - 0.6, 1.4, 0.16)
                railing(P, bx - (along - 0.6) / 2, by + ny * 0.6, bx + (along - 0.6) / 2, by + ny * 0.6, fl * fh + 0.16)
    # 側面の窓(少なめ)
    for side in [s for s in ("-x", "+x", "-y", "+y") if s != face]:
        if rng.random() < 0.5:
            continue
        sa, _ = side_dims(w, d, side)
        m = max(1, int(sa // 4.0))
        for fl in range(1, floors):
            for k in range(m):
                t = -sa / 2 + (k + 0.5) * sa / m
                window(P, cx, cy, w, d, side, t, fl * fh + 1.6, 1.0, 1.2, sill=False)
    # 雨樋、室外機、屋上
    gx, gy = wall_point(cx, cy, w, d, face, along / 2 - 0.25, 0.1)
    P.cyl(gx, gy, h / 2, 0.06, h, 8)
    # 袖看板(壁から通りへ突き出す縦長の板)。日本の商店街の顔
    if floors >= 2 and rng.random() < 0.8:
        sx_, sy_ = wall_point(cx, cy, w, d, face, -along / 2 + 0.6, 0.75)
        z0, z1 = fh + 0.8, min(h - 0.6, fh + 0.8 + 3.0)
        if face in ("-x", "+x"):
            P.box(sx_, sy_, (z0 + z1) / 2, 1.3, 0.16, z1 - z0)
            P.box(sx_ - nx * 0.4, sy_, z1 - 0.3, 0.7, 0.06, 0.06)
            P.box(sx_ - nx * 0.4, sy_, z0 + 0.3, 0.7, 0.06, 0.06)
        else:
            P.box(sx_, sy_, (z0 + z1) / 2, 0.16, 1.3, z1 - z0)
            P.box(sx_, sy_ - ny * 0.4, z1 - 0.3, 0.06, 0.7, 0.06)
            P.box(sx_, sy_ - ny * 0.4, z0 + 0.3, 0.06, 0.7, 0.06)
    # 立て看板(A型)とプランター、シャッターボックス
    ax_, ay_ = wall_point(cx, cy, w, d, face, rng.uniform(-along * 0.3, along * 0.3), 1.6)
    if rng.random() < 0.6:
        if face in ("-x", "+x"):
            P.box(ax_, ay_, 0.5, 0.45, 0.6, 1.0)
        else:
            P.box(ax_, ay_, 0.5, 0.6, 0.45, 1.0)
    for k in range(rng.randint(0, 2)):
        px_, py_ = wall_point(cx, cy, w, d, face, (-1) ** k * (along / 2 - 1.0), 0.6)
        P.box(px_, py_, 0.25, 0.5, 0.5, 0.5)
    bx_, by_ = wall_point(cx, cy, w, d, face, 0.0, 0.05)
    if face in ("-x", "+x"):
        P.box(bx_, by_, 3.05, 0.35, glass_w + 0.8, 0.3)
    else:
        P.box(bx_, by_, 3.05, glass_w + 0.8, 0.35, 0.3)
    for _ in range(rng.randint(1, 3)):
        side = rng.choice([s for s in ("-x", "+x", "-y", "+y") if s != face])
        sa, _ = side_dims(w, d, side)
        ac_unit(P, cx, cy, w, d, side, rng.uniform(-sa / 2 + 1, sa / 2 - 1), rng.uniform(1.0, h - 1.5))
    P.box(cx, cy, h + 0.25, w + 0.2, d + 0.2, 0.5)                          # パラペット
    P.cyl(cx + w * 0.25, cy + d * 0.2, h + 1.2, 0.9, 1.4, 12)                # 給水タンク
    P.box(cx + w * 0.25, cy + d * 0.2, h + 0.35, 2.4, 2.4, 0.2)
    if rng.random() < 0.5:
        P.box(cx - w * 0.25, cy - d * 0.2, h + 1.1, 2.6, 2.2, 2.2)           # 階段室
    return P.join()


def apartment(cx, cy, w, d, floors, face, rng, idx):
    P = Parts(f"apt{idx}")
    fh = 2.9
    h = floors * fh + 0.4
    nx, ny = facing(face)
    along, depth = side_dims(w, d, face)
    P.box(cx, cy, h / 2, w, d, h)
    n = max(2, int(along // 3.4))
    cell = along / n
    for fl in range(floors):
        z0 = fl * fh
        bx, by = wall_point(cx, cy, w, d, face, 0.0, 0.7)
        # ベランダの床と手すり板
        if face in ("-x", "+x"):
            P.box(bx, by, z0 + 0.08, 1.4, along, 0.16)
            P.box(bx + nx * 0.65, by, z0 + 0.65, 0.08, along, 1.1)
            P.bar((bx + nx * 0.65, by - along / 2, z0 + 1.22), (bx + nx * 0.65, by + along / 2, z0 + 1.22), 0.03)
        else:
            P.box(bx, by, z0 + 0.08, along, 1.4, 0.16)
            P.box(bx, by + ny * 0.65, z0 + 0.65, along, 0.08, 1.1)
            P.bar((bx - along / 2, by + ny * 0.65, z0 + 1.22), (bx + along / 2, by + ny * 0.65, z0 + 1.22), 0.03)
        for k in range(n):
            t = -along / 2 + (k + 0.5) * cell
            window(P, cx, cy, w, d, face, t - cell * 0.15, z0 + 1.45, cell * 0.45, 1.9, sill=False)   # 掃き出し窓
            # 仕切り板
            if k < n - 1:
                px, py = wall_point(cx, cy, w, d, face, -along / 2 + (k + 1) * cell, 0.7)
                if face in ("-x", "+x"):
                    P.box(px, py, z0 + 1.0, 1.3, 0.06, 1.8)
                else:
                    P.box(px, py, z0 + 1.0, 0.06, 1.3, 1.8)
    # 外階段(正面の端)
    sx, sy = wall_point(cx, cy, w, d, face, along / 2 + 1.4, 0.0)
    if face in ("-x", "+x"):
        P.box(sx, sy, h / 2, 2.6, 2.6, h)
        for fl in range(1, floors + 1):
            P.box(sx + nx * 1.4, sy, fl * fh - 0.3, 0.12, 2.6, 0.6)
    else:
        P.box(sx, sy, h / 2, 2.6, 2.6, h)
        for fl in range(1, floors + 1):
            P.box(sx, sy + ny * 1.4, fl * fh - 0.3, 2.6, 0.12, 0.6)
    P.box(cx, cy, h + 0.3, w + 0.2, d + 0.2, 0.6)
    P.cyl(cx, cy, h + 1.5, 1.2, 1.8, 12)
    P.box(cx, cy, h + 0.45, 3.0, 3.0, 0.3)
    for _ in range(rng.randint(2, 5)):
        side = rng.choice([s for s in ("-x", "+x", "-y", "+y") if s != face])
        sa, _ = side_dims(w, d, side)
        ac_unit(P, cx, cy, w, d, side, rng.uniform(-sa / 2 + 1, sa / 2 - 1), rng.uniform(0.6, h - 1.5))
    return P.join()


def house(cx, cy, w, d, face, rng, idx):
    P = Parts(f"house{idx}")
    nx, ny = facing(face)
    along, depth = side_dims(w, d, face)
    h = 5.6
    bw, bd = w * 0.72, d * 0.72
    # 敷地の奥に寄せる
    bcx = cx - nx * (w - bw) / 2 * 0.6
    bcy = cy - ny * (d - bd) / 2 * 0.6
    P.box(bcx, bcy, h / 2, bw, bd, h)
    ridge_along = "x" if bw >= bd else "y"
    P.prism(bcx, bcy, h, bw + 1.0, bd + 1.0, h, h + (min(bw, bd) * 0.35), ridge_along)
    P.box(bcx, bcy, h - 0.1, bw + 1.0, bd + 1.0, 0.2)                          # 軒
    # 窓と玄関
    for fl in (0, 1):
        z = 1.4 + fl * 2.8
        for t in (-bw * 0.28, bw * 0.28) if face in ("-y", "+y") else (-bd * 0.28, bd * 0.28):
            window(P, bcx, bcy, bw, bd, face, t, z, 1.5, 1.2)
    dx, dy = wall_point(bcx, bcy, bw, bd, face, 0.0, 0.0)
    if face in ("-x", "+x"):
        P.box(dx + nx * 0.05, dy, 1.05, 0.1, 1.0, 2.1)
        P.box(dx + nx * 0.6, dy, 2.35, 1.2, 1.8, 0.1)
    else:
        P.box(dx, dy + ny * 0.05, 1.05, 1.0, 0.1, 2.1)
        P.box(dx, dy + ny * 0.6, 2.35, 1.8, 1.2, 0.1)
    # 塀(通り側)と門柱
    fx, fy = wall_point(cx, cy, w, d, face, 0.0, -0.15)
    if face in ("-x", "+x"):
        P.box(fx, fy - along * 0.32, 0.6, 0.2, along * 0.36, 1.2)
        P.box(fx, fy + along * 0.32, 0.6, 0.2, along * 0.36, 1.2)
        P.box(fx, fy - along * 0.14, 0.8, 0.35, 0.35, 1.6)
        P.box(fx, fy + along * 0.14, 0.8, 0.35, 0.35, 1.6)
    else:
        P.box(fx - along * 0.32, fy, 0.6, along * 0.36, 0.2, 1.2)
        P.box(fx + along * 0.32, fy, 0.6, along * 0.36, 0.2, 1.2)
        P.box(fx - along * 0.14, fy, 0.8, 0.35, 0.35, 1.6)
        P.box(fx + along * 0.14, fy, 0.8, 0.35, 0.35, 1.6)
    # カーポート(片側)
    if rng.random() < 0.7:
        px, py = wall_point(cx, cy, w, d, face, along * 0.3, -2.2)
        if face in ("-x", "+x"):
            P.box(px, py, 2.6, 4.6, 3.0, 0.08)
            for s in (-1, 1):
                P.cyl(px - nx * 2.0, py + s * 1.3, 1.3, 0.06, 2.6, 8)
        else:
            P.box(px, py, 2.6, 3.0, 4.6, 0.08)
            for s in (-1, 1):
                P.cyl(px + s * 1.3, py - ny * 2.0, 1.3, 0.06, 2.6, 8)
    ac_unit(P, bcx, bcy, bw, bd, rng.choice([s for s in ("-x", "+x", "-y", "+y") if s != face]), 0.0, 0.5)
    return P.join()


def konbini(cx, cy, w, d, face, rng, idx):
    P = Parts(f"konbini{idx}")
    nx, ny = facing(face)
    along, depth = side_dims(w, d, face)
    h = 4.4
    # 建物は敷地の奥、前は駐車場
    bcx = cx - nx * (w * 0.5 - d * 0.0) * 0.0
    P.box(cx, cy, h / 2, w, d, h)
    x, y = wall_point(cx, cy, w, d, face, 0.0, 0.0)
    gw = along - 1.2
    if face in ("-x", "+x"):
        P.box(x - nx * 0.3, y, 1.5, 0.08, gw, 2.8)
        for k in range(1, int(gw // 1.6)):
            P.box(x - nx * 0.3, y - gw / 2 + k * 1.6, 1.5, 0.12, 0.1, 2.8)
        P.box(x + nx * 0.2, y, h - 0.55, 0.4, along + 0.6, 1.0)             # 看板帯
        P.box(x + nx * 1.4, y, 3.05, 2.6, gw + 0.8, 0.1)                     # 庇
        for s in (-1, 1):
            P.cyl(x + nx * 2.5, y + s * (gw / 2 - 0.2), 1.5, 0.08, 3.0, 8)
    else:
        P.box(x, y - ny * 0.3, 1.5, gw, 0.08, 2.8)
        for k in range(1, int(gw // 1.6)):
            P.box(x - gw / 2 + k * 1.6, y - ny * 0.3, 1.5, 0.1, 0.12, 2.8)
        P.box(x, y + ny * 0.2, h - 0.55, along + 0.6, 0.4, 1.0)
        P.box(x, y + ny * 1.4, 3.05, gw + 0.8, 2.6, 0.1)
        for s in (-1, 1):
            P.cyl(x + s * (gw / 2 - 0.2), y + ny * 2.5, 1.5, 0.08, 3.0, 8)
    for side in [s for s in ("-x", "+x", "-y", "+y") if s != face]:
        sa, _ = side_dims(w, d, side)
        px, py = wall_point(cx, cy, w, d, side, 0.0, 0.2)
        if side in ("-x", "+x"):
            P.box(px, py, h - 0.55, 0.4, sa + 0.6, 1.0)
        else:
            P.box(px, py, h - 0.55, sa + 0.6, 0.4, 1.0)
    P.box(cx, cy, h + 0.2, w + 0.2, d + 0.2, 0.4)
    P.box(cx + w * 0.2, cy - d * 0.2, h + 0.9, 2.0, 1.6, 1.4)                # 屋上機器
    ac_unit(P, cx, cy, w, d, rng.choice([s for s in ("-x", "+x", "-y", "+y") if s != face]), 0.0, 1.0)
    return P.join()


def parking(cx, cy, w, d, face, rng, idx):
    """フェンスと駐車枠。車は assets 側で置く。"""
    P = Parts(f"parking{idx}")
    nx, ny = facing(face)
    along, depth = side_dims(w, d, face)
    # フェンス(正面以外の3辺)
    for side in [s for s in ("-x", "+x", "-y", "+y") if s != face]:
        sa, _ = side_dims(w, d, side)
        n = int(sa // 2.5) + 1
        for k in range(n + 1):
            t = -sa / 2 + k * sa / n
            px, py = wall_point(cx, cy, w, d, side, t, -0.1)
            P.cyl(px, py, 0.9, 0.04, 1.8, 6)
        a = wall_point(cx, cy, w, d, side, -sa / 2, -0.1)
        b = wall_point(cx, cy, w, d, side, sa / 2, -0.1)
        for z in (0.6, 1.2, 1.75):
            P.bar((a[0], a[1], z), (b[0], b[1], z), 0.02)
    # 駐車枠の白線
    slots = int(along // 2.6)
    for k in range(slots + 1):
        t = -along / 2 + k * along / slots
        px, py = wall_point(cx, cy, w, d, face, t, -depth * 0.5)
        if face in ("-x", "+x"):
            P.box(px, py, 0.01, depth * 0.45, 0.12, 0.02)
        else:
            P.box(px, py, 0.01, 0.12, depth * 0.45, 0.02)
    return P.join()


# ---------------------------------------------------------------- 街路

def street(rng):
    """車道・歩道・縁石・路面標示・電柱・電線・信号・街灯・小物。"""
    S = Parts("street")
    ylo, yhi = -70.0, 140.0
    # 歩道と縁石(大通り)
    for sx in (-1, 1):
        segs = [(ylo, CROSS[0] - XW), (CROSS[0] + XW, CROSS[1] - XW), (CROSS[1] + XW, yhi)]
        for y0, y1 in segs:
            # 縁石は歩道の箱そのもの(別の箱を重ねると天面が 5mm 差で
            # Z ファイトし、遠くでちらついた。実測)
            S.box(sx * (ROAD + WALK / 2), (y0 + y1) / 2, 0.075, WALK, y1 - y0, 0.15)
    # 横町の歩道
    for cy in CROSS:
        for sy in (-1, 1):
            # 角は大通りの歩道と重なる(同じ天面で Z ファイト)ので CURB から
            for x0, x1 in ((-70.0, -CURB), (CURB, 70.0)):
                S.box((x0 + x1) / 2, cy + sy * (XW + WALK / 2), 0.075, x1 - x0, WALK, 0.15)
    # 中央線(破線)・外側線・停止線・横断歩道
    y = ylo
    while y < yhi:
        if not any(abs(y - c) < XW + 4 for c in CROSS):
            S.box(0.0, y + 2.5, 0.015, 0.15, 5.0, 0.03)
        y += 10.0
    for sx in (-1, 1):
        for y0, y1 in [(ylo, CROSS[0] - XW - 4), (CROSS[0] + XW + 4, CROSS[1] - XW - 4), (CROSS[1] + XW + 4, yhi)]:
            S.box(sx * (ROAD - 0.6), (y0 + y1) / 2, 0.015, 0.15, y1 - y0, 0.03)
    for cy in CROSS:
        for sy in (-1, 1):
            yy = cy + sy * (XW + 1.4)
            for k in range(-4, 5):
                S.box(k * 1.1, yy, 0.015, 0.5, 2.4, 0.03)
            S.box(sy * 2.75, cy + sy * (XW + 3.2), 0.015, ROAD, 0.4, 0.03)       # 停止線
        for sx in (-1, 1):
            xx = sx * (ROAD + 1.4)
            for k in range(-3, 4):
                S.box(xx, cy + k * 1.1, 0.015, 2.4, 0.5, 0.03)
    # マンホール
    for y in range(int(ylo) + 7, int(yhi), 23):
        S.cyl(rng.choice((-2.4, 2.4)), y, 0.015, 0.35, 0.03, 16)
    # 電柱(片側、22m 間隔)と電線、街灯(反対側)
    poles = []
    for y in range(int(ylo) + 6, int(yhi), 22):
        if any(abs(y - c) < XW + 3 for c in CROSS):
            y += 4
        px = ROAD + 0.9
        S.cyl(px, y, 5.5, 0.16, 11.0, 10)
        S.box(px, y, 9.6, 0.14, 2.6, 0.14)
        S.box(px, y, 10.4, 0.14, 2.0, 0.14)
        if rng.random() < 0.4:
            S.cyl(px + 0.4, y, 8.4, 0.35, 1.0, 10)                          # 変圧器
        poles.append((px, y))
    for (x0, y0), (x1, y1) in zip(poles, poles[1:]):
        for dy_, z in ((-1.2, 9.65), (0.0, 9.65), (1.2, 9.65), (-0.9, 10.45), (0.9, 10.45)):
            # 少し垂らす
            mid = ((x0 + x1) / 2, (y0 + y1) / 2, z - 0.35)
            S.bar((x0, y0 + dy_, z), mid[:2] + (mid[2],), 0.018)
            S.bar(mid[:2] + (mid[2],), (x1, y1 + dy_, z), 0.018)
    for y in range(int(ylo) + 14, int(yhi), 26):
        if any(abs(y - c) < XW + 3 for c in CROSS):
            continue
        lx = -(ROAD + 0.8)
        S.cyl(lx, y, 3.0, 0.08, 6.0, 8)
        S.bar((lx, y, 5.9), (lx + 1.6, y, 6.3), 0.05)
        S.box(lx + 1.7, y, 6.25, 0.5, 0.28, 0.2)
    # 信号機(交差点の各角)、ガードレール(交差点付近)
    for cy in CROSS:
        for sx, sy in ((1, -1), (-1, 1), (1, 1), (-1, -1)):
            px, py = sx * (ROAD + 0.7), cy + sy * (XW + 0.7)
            S.cyl(px, py, 2.9, 0.09, 5.8, 8)
            ax = px - sx * 3.2
            S.bar((px, py, 5.6), (ax, py, 5.6), 0.06)
            S.box(ax + sx * 0.6, py, 5.2, 1.2, 0.35, 0.4)
            for k in range(3):
                S.cyl(ax + sx * (0.2 + 0.4 * k) - sx * 0.2, py - sy * 0.22, 5.2, 0.13, 0.06, 10,
                      rot=(math.radians(90), 0, 0))
            S.box(px, py, 3.2, 0.3, 0.3, 0.6)                                   # 押しボタン箱
        for sx in (-1, 1):
            for sy in (-1, 1):
                y0 = cy + sy * (XW + 2.0)
                y1 = cy + sy * (XW + 14.0)
                for k in range(7):
                    yy = y0 + (y1 - y0) * k / 6
                    S.cyl(sx * (ROAD + 0.3), yy, 0.4, 0.05, 0.8, 8)
                S.box(sx * (ROAD + 0.3), (y0 + y1) / 2, 0.68, 0.06, abs(y1 - y0), 0.3)
    # 自販機・バス停・ポスト
    for y in (-30.0, 22.0, 46.0, 96.0):
        sx = rng.choice((-1, 1))
        x = sx * (ROAD + 2.9)
        S.box(x, y, 0.92, 0.8, 1.05, 1.84)
        S.box(x - sx * 0.42, y, 1.05, 0.04, 0.85, 1.2)
    for y in (12.0, 88.0):
        S.cyl(-(ROAD + 1.0), y, 1.3, 0.04, 2.6, 8)
        S.cyl(-(ROAD + 1.0), y, 2.4, 0.45, 0.06, 16, rot=(math.radians(90), 0, 0))
    S.cyl(ROAD + 1.2, 30.0, 0.55, 0.22, 1.1, 12)
    S.box(ROAD + 1.2, 30.0, 1.2, 0.5, 0.5, 0.2)
    # 植樹枡(街路樹の根元の縁石)
    for y in range(-50, 132, 18):
        if any(abs(y - c) < XW + 6 for c in CROSS):
            continue
        for sx in (-1, 1):
            x = sx * (ROAD + 1.9)
            S.box(x, y, 0.19, 1.6, 1.6, 0.08)
            S.box(x, y, 0.1, 1.3, 1.3, 0.12)
    # 通りをまたぐ電線(電柱から反対側の街灯・建物へ)
    for k, (px, py) in enumerate(poles):
        if k % 2 == 0:
            S.bar((px, py, 9.9), (-(ROAD + 1.0), py + 3.0, 8.4), 0.018)
            S.bar((px, py, 9.6), (-(ROAD + 1.0), py + 3.0, 8.1), 0.018)
    # 歩道の点字ブロック帯(交差点の手前)と側溝の蓋
    for cy in CROSS:
        for sx in (-1, 1):
            for sy in (-1, 1):
                S.box(sx * (ROAD + 1.6), cy + sy * (XW + 1.0), 0.175, 2.4, 0.4, 0.03)   # 底が歩道の天面(0.15)に重ならないよう浮かす
    for y in range(int(ylo), int(yhi), 2):
        if any(abs(y - c) < XW + 1 for c in CROSS):
            continue
        S.box(-(ROAD - 0.25), y + 1.0, 0.015, 0.45, 1.9, 0.03)
    # 遠景: 通りの先(北)に高いビル群、南に低い街並み
    for k in range(9):
        bx = rng.uniform(-70, 70)
        by = rng.uniform(190, 320)
        bw, bd, bh = rng.uniform(16, 30), rng.uniform(16, 30), rng.uniform(30, 75)
        S.box(bx, by, bh / 2, bw, bd, bh)
        S.box(bx, by, bh + 0.4, bw + 0.6, bd + 0.6, 0.8)
        for fl in range(2, int(bh // 3.4)):
            S.box(bx, by - bd / 2 - 0.06, fl * 3.4, bw - 2.0, 0.12, 1.5)
    return S.join()


# ---------------------------------------------------------------- 街区の割付

def layout(rng):
    made = []
    idx = 0
    # 大通りに面した敷地を、街区ごとに y 方向へ割る
    for sx in (-1, 1):
        face = "-x" if sx > 0 else "+x"
        for (y0, y1) in ((-64.0, -XW - 4.0), (XW + 4.0, CROSS[1] - XW - 4.0), (CROSS[1] + XW + 4.0, 136.0)):
            y = y0
            while y < y1 - 7.0:
                kind = rng.choices(("shop", "apt", "house", "konbini", "parking"),
                                   weights=(5, 2, 3, 1, 1))[0]
                if kind == "konbini":
                    w_, d_ = 18.0, 12.0
                    lot = w_ + 2.0
                    setback = 10.0
                elif kind == "parking":
                    w_, d_ = rng.uniform(12, 18), 11.0
                    lot = w_ + 1.0
                    setback = 0.0
                elif kind == "house":
                    w_, d_ = rng.uniform(9, 12), rng.uniform(10, 13)
                    lot = w_ + 0.8
                    setback = 0.0
                elif kind == "apt":
                    w_, d_ = rng.uniform(16, 26), rng.uniform(9, 12)
                    lot = w_ + 4.0
                    setback = 1.2
                else:
                    w_, d_ = rng.uniform(7, 13), rng.uniform(9, 14)
                    lot = w_ + rng.uniform(0.3, 1.5)
                    setback = 0.0
                if y + lot > y1:
                    break
                cy = y + lot / 2
                cx = sx * (CURB + setback + d_ / 2)
                if kind == "shop":
                    made.append(shophouse(cx, cy, d_, w_, rng.choice((2, 2, 3, 3, 4)), face, rng, idx))
                elif kind == "apt":
                    made.append(apartment(cx, cy, d_, w_, rng.choice((3, 4, 5)), face, rng, idx))
                elif kind == "house":
                    made.append(house(cx, cy, d_, w_, face, rng, idx))
                elif kind == "konbini":
                    made.append(konbini(cx, cy, d_, w_, face, rng, idx))
                    made.append(parking(sx * (CURB + setback / 2), cy, setback - 0.5, w_ + 1.0, face, rng, idx))
                    KONBINI_LOTS.append((sx, cy, setback))
                else:
                    made.append(parking(cx, cy, d_, w_, face, rng, idx))
                    PARKING_LOTS.append((cx, cy, d_, w_, face))
                idx += 1
                y += lot
    # 横町に面した敷地(交差点から離れた所に、家や店)
    for cy_c in CROSS:
        for sy in (-1, 1):
            face = "-y" if sy > 0 else "+y"
            for sx in (-1, 1):
                x = CURB + 2.0
                while x < 60.0:
                    kind = rng.choices(("shop", "house", "apt"), weights=(3, 4, 1))[0]
                    w_ = rng.uniform(8, 13) if kind != "apt" else rng.uniform(16, 22)
                    d_ = rng.uniform(9, 13)
                    cx = sx * (x + w_ / 2)
                    cy = cy_c + sy * (XW + WALK + d_ / 2 + (1.2 if kind == "apt" else 0.0))
                    if kind == "shop":
                        made.append(shophouse(cx, cy, w_, d_, rng.choice((2, 3)), face, rng, idx))
                    elif kind == "house":
                        made.append(house(cx, cy, w_, d_, face, rng, idx))
                    else:
                        made.append(apartment(cx, cy, w_, d_, rng.choice((3, 4)), face, rng, idx))
                    idx += 1
                    x += w_ + rng.uniform(0.5, 2.0)
    return made


KONBINI_LOTS = []
PARKING_LOTS = []


# ---------------------------------------------------------------- アセット

def flatten(objs, name):
    """アセットを1つのメッシュに焼く(モディファイア適用 + 結合)。

    オブジェクトの複製で親子・コンストレイント・ミラーの基準を付け替える
    やり方は、車輪が歩道に転がる(実測)など事故が絶えなかった。1枚に
    焼けば複製は単なるメッシュ共有になる。
    """
    meshes = [o for o in objs if o.type == "MESH" and not o.hide_render]
    if not meshes:
        return None
    others = [o.name for o in objs if o not in meshes]     # 結合で消える前に名前で控える
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.convert(target="MESH")      # モディファイア(アーマチュア・ミラー・サブサーフ)を適用
    bpy.ops.object.join()
    o = bpy.context.object
    o.parent = None
    o.constraints.clear()
    o.name = name
    for name_ in others:
        other = bpy.data.objects.get(name_)
        if other is not None and other is not o:
            bpy.data.objects.remove(other, do_unlink=True)
    bpy.context.view_layer.update()
    return o


def place_asset(o, height):
    bb = td.bounds([o])
    size = bb[1] - bb[0]
    s = height / max(size.z, 1e-6)
    td.transform([o], Matrix.Scale(s, 4))
    bb = td.bounds([o])
    td.transform([o], Matrix.Translation(Vector((1000.0 - (bb[0].x + bb[1].x) / 2,
                                                 1000.0 - (bb[0].y + bb[1].y) / 2, -bb[0].z))))


def duplicate(o, x, y, rot_deg, scale=1.0):
    """1枚に焼いたアセットのリンク複製(メッシュ共有)。"""
    base = Vector((1000.0, 1000.0, 0.0))
    c = o.copy()
    bpy.context.scene.collection.objects.link(c)
    m = (Matrix.Translation(Vector((x, y, 0))) @ Matrix.Rotation(math.radians(rot_deg), 4, "Z")
         @ Matrix.Scale(scale, 4) @ Matrix.Translation(-base))
    c.matrix_world = m @ o.matrix_world
    c.hide_render = False
    c.hide_viewport = False
    return c


def assets(rng):
    made = []
    lib = {}
    kinds = {"european-maple": "trees", "police-car": "cars", "nypd_toyota": "cars",
             "lancia-delta": "cars", "hyundai-veloster": "cars", "audi_r8": "cars",
             "mclaren_720s": "cars", "man_01": "people",
             "standing-cool-bald": "people", "stylized-male": "people", "anime-girl": "people"}
    for pat, height in (("european-maple", 5.6), ("police-car", 1.5), ("nypd_toyota", 1.5),
                        ("lancia-delta", 1.45), ("hyundai-veloster", 1.4), ("audi_r8", 1.25),
                        ("mclaren_720s", 1.2),   # メルセデス SLR は複製すると STEP0 の後のレンダで落ちる(実測)
                        ("man_01", 1.75), ("standing-cool-bald", 1.8), ("stylized-male", 1.75),
                        ("anime-girl", 1.6), ("manchester-acacia", 0.8), ("trash_can", 1.0)):
        if kinds.get(pat) in SKIP or pat in SKIP:
            continue
        objs = td.load_lot(pat)
        if not objs:
            say(f"見つからない: {pat}")
            continue
        o = flatten(objs, f"asset_{pat}")
        if o is None:
            continue
        place_asset(o, height)
        o.hide_render = True          # 原本は写らない。複製だけ写す
        o.hide_viewport = True
        lib[pat] = o
        say(f"  {pat}: {len(o.data.polygons)} 面")

    def put(pat, x, y, rot, scale=1.0):
        if pat not in lib:
            return
        made.append(duplicate(lib[pat], x, y, rot, scale))

    cars = ["police-car", "nypd_toyota", "lancia-delta", "hyundai-veloster", "audi_r8",
            "mclaren_720s"]
    # 街路樹(植樹枡): 大通りの歩道、18m ごと、電柱と街灯を避ける
    for y in range(-50, 132, 18):
        if any(abs(y - c) < XW + 6 for c in CROSS):
            continue
        for sx in (-1, 1):
            put("european-maple", sx * (ROAD + 1.9), y,
                rng.uniform(0, 360), rng.uniform(0.8, 1.1))
    # 走っている車(左側通行: 進行方向左の車線)
    # アセットの正面は -y(実測)。北向き(+y、左側通行なので x<0)は 180 度回す
    y = -60.0
    while y < 130:
        put(rng.choice(cars), -2.6, y, 180)        # 北向き(左車線)
        y += rng.uniform(16, 34)
    y = -48.0
    while y < 130:
        put(rng.choice(cars), 2.6, y, 0)           # 南向き
        y += rng.uniform(18, 36)
    for cy in CROSS:
        for x in (-28.0, 24.0, 44.0):
            side = rng.choice((-2.6, 2.6))
            put(rng.choice(cars), x, cy + side, -90 if side < 0 else 90)   # 左側通行
    # 駐車場・コンビニの車
    for (cx, cy, d_, w_, face) in PARKING_LOTS:
        along, depth = side_dims(d_, w_, face)
        slots = int(along // 2.6)
        for k in range(slots):
            if rng.random() < 0.55:
                t = -along / 2 + (k + 0.5) * along / slots
                px, py = wall_point(cx, cy, d_, w_, face, t, -depth * 0.5)
                put(rng.choice(cars), px, py, (0 if face in ("-x", "+x") else 90) + rng.uniform(-3, 3))
    for (sx, cy, setback) in KONBINI_LOTS:
        for k in range(3):
            if rng.random() < 0.7:
                put(rng.choice(cars), sx * (CURB + setback / 2), cy - 6 + k * 3.0, 90 + rng.uniform(-3, 3))
    # 人: 歩道に 18 人
    people = ["man_01", "standing-cool-bald", "stylized-male", "anime-girl"]
    n = 0
    while n < 18:
        sx = rng.choice((-1, 1))
        y = rng.uniform(-45, 125)
        if any(abs(y - c) < XW + 2 for c in CROSS):
            continue
        put(rng.choice(people), sx * (ROAD + rng.uniform(0.9, 2.9)), y, rng.uniform(0, 360))
        n += 1
    for cy in CROSS:
        for k in range(3):
            put(rng.choice(people), rng.uniform(-3, 3), cy + rng.choice((-1, 1)) * (XW + 1.4), rng.choice((0, 180)))
    for y in (12.5, 88.5):
        put("manchester-acacia", -(ROAD + 2.4), y + 2.5, 90)
        put("trash_can", -(ROAD + 2.6), y + 5.0, 0)
    return made


# ---------------------------------------------------------------- 全体

def stage():
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=1)
    ground = bpy.context.object
    ground.scale = (4000, 4000, 1)
    ground.location = (0, 30, -0.02)
    ground.name = "FP_ground"
    cd = bpy.data.cameras.new("C")
    cd.lens = 28.0
    # 6000 だと深度バッファの精度が落ち、重なった面がちらつく。町は 300m
    cd.clip_start = 0.3
    cd.clip_end = 1200
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (-3.2, -38.0, 1.6)
    cam.rotation_euler = (math.radians(89.0), 0.0, math.radians(-3.0))
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1)
        bg.inputs[1].default_value = 0.15
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = math.radians(2.0)
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(50), 0, math.radians(-35))
    return cam, ground


def main():
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)
    rng = random.Random(SEED)
    meshes = [o for o in layout(rng) if o is not None]
    say(f"建物 {len(meshes)} 棟")
    meshes.append(street(rng))
    meshes += assets(rng)
    say(f"メッシュ {len(meshes)} 個(アセット込み)")
    cam, ground = stage()
    dm.grey([o for o in meshes if o.type == "MESH"] + [ground])
    sc = bpy.context.scene
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.fp_auto_style = STYLE
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_x = 1920
    sc.render.resolution_y = 1080
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes + [ground]:
        if o.type == "MESH" and not o.hide_viewport:
            o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "town_pre.blend"))   # STEP0 前(調査用)
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    say(f"STEP0 done: 距離 {sc.fp_lw_far_start:.1f}..{sc.fp_lw_far_end:.1f} 密度 {sc.fp_lw_density:.3f}")
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = 'MONO_LIGHT'
    sc.fp_enable_compositor_view = True
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "town.blend"))
    say(f"保存 {OUT / 'town.blend'}")


if __name__ == "__main__":
    main()
