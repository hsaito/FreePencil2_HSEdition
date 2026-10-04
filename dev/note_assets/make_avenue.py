"""ビル街の大通りを低空で飛ぶ(線画デモ用。窓の密度は控えめ、線はくっきり)。

  blender -b --factory-startup --python make_avenue.py -- --wire [--res 1600] [--seed 11] [--cam-y -120] [--cam-z 16]
      構図の確認(Workbench の凹凸強調。STEP0 なし、数秒)
  blender -b --factory-startup --python make_avenue.py -- --full [--res 1920] [--samples 8]
      STEP0(手描き背景)+ 静止画(線画 / 精密)を撮る

作りの方針:
  - 大通り(半幅 26m)+ 歩道。奥へ 2.4km。横道(ビルの切れ目)が約 90m ごとにあり、奥行きと光が抜ける
  - ビルは 3 種類の高さ(中層 / 高層 / 超高層)。セットバックと屋上の冠。窓は大きめの 4 種類
  - 高架の梁(ガントリー)を数百メートルごとにまたがせる(くぐる飛行の手がかり)
  - 参考の AKIRA ほど詰めない(線が軽減の領域に入らず、くっきり残る密度)
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "avenue"))).resolve()
RES = int(arg("--res", "1600"))
SEED = int(arg("--seed", "11"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))

import bpy          # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402

from town_kit import MB, facade_matrix   # noqa: E402

RW = float(arg("--rw", "26"))          # 大通りの半幅
SIDE = 6.0                              # 歩道
Y0, Y1 = float(arg("--y0", "-400")), float(arg("--y1", "2400"))
CAM = (float(arg("--cam-x", "0")), float(arg("--cam-y", "-120")), float(arg("--cam-z", "16")))
LENS = float(arg("--lens", "24"))


def say(m):
    print(f"@@@ {m}", flush=True)


# ---------------------------------------------------------------- 窓(ローカル: 正面 y=0、外が -y)
# どれも「1 つの窓が画面で 12px 以上」になる大きさ(4K で、遠景も細かくなりすぎない)

def style_punched(mb, W, h, fh, rng):
    pitch = rng.choice((3.0, 3.6, 4.4)) * PS
    ww, wh = pitch * rng.uniform(0.55, 0.68), fh * rng.uniform(0.5, 0.62)
    ncol = max(2, int(W / pitch))
    for fl in range(int(h / fh)):
        z = fl * fh + fh * 0.5
        for c in range(ncol):
            mb.box(-W / 2 + (c + 0.5) * W / ncol, -0.07, z, ww, 0.14, wh)


def style_band(mb, W, h, fh, rng):
    wh = fh * rng.uniform(0.5, 0.62)
    for fl in range(int(h / fh)):
        mb.box(0, -0.06, fl * fh + fh * 0.5, W, 0.12, wh)
    k = max(1, int(W / rng.choice((10.0, 14.0, 20.0))))
    for i in range(k + 1):
        mb.box(-W / 2 + i * W / k, -0.12, h / 2, 0.3, 0.24, h)


def style_fins(mb, W, h, fh, rng):
    pitch = rng.choice((1.2, 1.5, 1.8))
    k = max(2, int(W / pitch))
    for i in range(k + 1):
        mb.box(-W / 2 + i * W / k, -0.14, h / 2, 0.14, 0.28, h)
    every = rng.choice((4, 6, 8))
    for fl in range(every, int(h / fh), every):
        mb.box(0, -0.25, fl * fh, W, 0.5, 0.5)


def style_grid(mb, W, h, fh, rng):
    bay = rng.choice((6.0, 8.0, 10.0))
    k = max(1, int(W / bay))
    for i in range(k + 1):
        mb.box(-W / 2 + i * W / k, -0.18, h / 2, 0.4, 0.36, h)
    per = rng.choice((2, 3))
    for fl in range(0, int(h / fh), per):
        mb.box(0, -0.16, fl * fh, W, 0.32, 0.35)


STYLES = (style_punched, style_band, style_grid)      # 細かい縦線が並ぶ窓(リブ)は使わない
STYLE_W = [float(v) for v in arg("--styles-w", "1,1,1").split(",")]   # 3 種の出やすさ
TALL = tuple(float(v) for v in arg("--tall-zone").split(":")) if arg("--tall-zone") else None
PS = float(arg("--pitch-scale", "1.0"))     # 窓の間隔の倍率(小さいほど詰まる)
FS = float(arg("--fh-scale", "1.0"))        # 階高の倍率


def crown(mb, W, D, h, rng):
    z = h
    mb.box(0, D / 2, z + 0.5, W + 0.6, D + 0.6, 1.0)
    z += 1.0
    for t in range(rng.randint(1, 3)):
        s = 0.76 - 0.16 * t
        th = rng.uniform(3.5, 8.0)
        mb.box(0, D / 2, z + th / 2, W * s, D * s, th)
        z += th
    if rng.random() < 0.6:
        sh = rng.uniform(10, 32)
        mb.box(0, D / 2, z + sh / 2, 0.7, 0.7, sh)
        for zz in np.linspace(z + sh * 0.3, z + sh * 0.9, 3):
            mb.box(0, D / 2, zz, 3.0, 0.1, 0.1)


def building(cx, cy, w, d, h, face, rng, idx, fh, style=None):
    """w = 通りに直角の奥行き、d = 通りに沿った長さ(town_kit_more.tower と同じ呼び方)。"""
    mat, along, depth = facade_matrix(cx, cy, w, d, face)
    mb = MB(f"b{idx}")
    style = style or rng.choices(STYLES, weights=STYLE_W)[0]
    mb.box(0, depth / 2, h / 2, along, depth, h)
    R = mat.to_3x3()
    for side in range(4):
        W = along if side % 2 == 0 else depth
        D = depth if side % 2 == 0 else along
        n_world = R @ (Matrix.Rotation(side * math.pi / 2, 3, "Z") @ Vector((0, -1, 0)))
        if not (side == 0 or n_world.y < -0.5):
            continue
        mb.push(np.array(Matrix.Translation((0, depth / 2, 0))
                         @ Matrix.Rotation(side * math.pi / 2, 4, "Z")
                         @ Matrix.Translation((0, -D / 2, 0))))
        style(mb, W, h, fh, rng)
        for s in (-1, 1):
            mb.box(s * W / 2, -0.25, h / 2, 0.8, 0.5, h)
        mb.pop()
    crown(mb, along, depth, h, rng)
    return mb.build(mat)


# ---------------------------------------------------------------- 並べる

def layout(rng):
    objs = []
    idx = 0
    for sx in (-1, 1):
        face = "-x" if sx > 0 else "+x"
        y = Y0 + rng.uniform(0, 10)
        while y < Y1:
            along = rng.uniform(34, 62)            # 1 棟の通りに沿った長さ
            depth = rng.uniform(26, 42)
            cy = y + along / 2
            far = max(0.0, y) / Y1
            kind = rng.random()
            fh = rng.choice((3.6, 4.0, 4.4)) * FS
            if TALL and TALL[0] <= cy <= TALL[1]:
                hb = rng.uniform(150, 260)                     # 見上げる区間は超高層で空を埋める
            elif kind < 0.45:
                hb = rng.uniform(28, 56)                       # 中層
            elif kind < 0.85:
                hb = rng.uniform(60, 110)                      # 高層
            else:
                hb = rng.uniform(130, 240)                     # 超高層
            x0 = sx * (RW + SIDE + depth / 2)
            objs.append(building(x0, cy, depth, along, hb, face, rng, idx, fh))
            idx += 1
            if hb > 60 and rng.random() < 0.85:                # セットバックの上層
                sb = rng.uniform(4.0, 9.0)
                dd = depth * rng.uniform(0.55, 0.8)
                aa = along * rng.uniform(0.6, 0.85)
                ht = hb * rng.uniform(0.5, 1.1) + 20
                objs.append(building(sx * (RW + SIDE + sb + dd / 2), cy, dd, aa, ht, face, rng, idx, fh))
                idx += 1
            y += along + rng.uniform(14, 34)                   # 横道(ビルの切れ目)
    return [o for o in objs if o is not None]


def gantries():
    """道をまたぐ高架の梁(くぐる飛行の手がかり)。"""
    mb = MB("gantries")
    for y in (220.0, 520.0, 860.0, 1250.0, 1700.0):
        h = 24.0
        for sx in (-1, 1):
            mb.box(sx * (RW + 1.5), y, h / 2, 3.0, 4.0, h)              # 橋脚
        mb.box(0, y, h + 2.0, 2 * RW + 6, 8.0, 4.0)                   # 桁(道幅全体)
        mb.box(0, y, h + 4.6, 2 * RW + 6, 9.0, 0.5)                   # 床
        for i in range(14):
            mb.box(-RW + i * (2 * RW / 13), y - 4.4, h + 5.4, 0.25, 0.25, 1.6)   # 欄干の支柱
        mb.box(0, y - 4.4, h + 6.1, 2 * RW + 6, 0.3, 0.3)
    return mb.build()


def road():
    mb = MB("road")
    L = Y1 - Y0 + 600
    for sx in (-1, 1):                                              # 縁石(歩道の段)
        mb.box(sx * (RW + SIDE / 2), (Y0 + Y1) / 2, 0.18, SIDE, L, 0.36)
    y = Y0
    while y < Y1 + 200:                                             # 中央線(太く・長く)
        mb.box(0, y, 0.02, 0.7, 12.0, 0.04)
        y += 26.0
    for sx in (-1, 1):                                              # 車線の実線
        mb.box(sx * (RW * 0.5), (Y0 + Y1) / 2, 0.02, 0.45, L, 0.04)
    return mb.build()


def stage():
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=1)
    ground = bpy.context.object
    ground.scale = (6000, 6000, 1)
    ground.location = (0, 600, -0.02)
    ground.name = "FP_ground"
    cd = bpy.data.cameras.new("C")
    cd.lens = LENS
    cd.clip_start = 0.5
    cd.clip_end = 6000
    cd.shift_y = float(arg("--shift-y", "0.05"))
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = CAM
    cam.rotation_euler = (math.radians(90.0 + float(arg("--tilt", "1.0"))), 0.0, 0.0)
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.75, 0.75, 0.77, 1)
        bg.inputs[1].default_value = float(arg("--ambient", "0.8"))
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = math.radians(2.0)
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(float(arg("--sun-el", "48"))), 0, math.radians(float(arg("--sun-az", "24"))))
    return ground


def grey(objs):
    m = bpy.data.materials.new("avenue_grey")
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
        b.inputs["Roughness"].default_value = 0.9
    for o in objs:
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(m)


def build_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
    rng = random.Random(SEED)
    blds = layout(rng)
    extra = [gantries(), road()]
    ground = stage()
    grey(blds + extra + [ground])
    faces = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    say(f"ビル {len(blds)} 棟 / 面 {faces:,}")
    return bpy.context.scene, blds + extra, ground


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sc, objs, ground = build_scene()
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.render.image_settings.file_format = "PNG"
    if "--wire" in ARGV:
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "FLAT"
        sh.color_type = "SINGLE"
        sh.single_color = (0.93, 0.93, 0.93)
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.cavity_ridge_factor = 1.6
        sh.cavity_valley_factor = 1.6
        sh.show_object_outline = True
        sc.render.film_transparent = False
        sc.render.filepath = str(OUT / f"{arg('--name', 'wire')}.png")
        bpy.ops.render.render(write_still=True)
        say("wire done")
        return
    import fp_batch
    fp_batch.install_addon()
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.render.engine = fp_batch.eevee_engine()
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    sc.eevee.taa_render_samples = int(arg("--samples", "8"))
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs + [ground]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "avenue_pre.blend"))
    if "--pre-only" in ARGV:
        say("saved pre")
        return
    sc.fp_auto_style = "BACKGROUND"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    say(f"STEP0 奥 {sc.fp_lw_far_start:.1f}..{sc.fp_lw_far_end:.1f} 密度 {sc.fp_lw_density:.3f} "
        f"減らし {sc.fp_lw_far_amount:.2f} 軽減 {sc.fp_lw_relief:.2f}")
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = "MONO_LIGHT"
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "avenue_bg.blend"))
    sc.render.filepath = str(OUT / "bg_default.png")
    bpy.ops.render.render(write_still=True)
    say("rendered bg_default")
    sc.fp_lw_far_amount = 0.0
    sc.render.filepath = str(OUT / "bg_relief_only.png")
    bpy.ops.render.render(write_still=True)
    say("rendered bg_relief_only")
    say("done")


if __name__ == "__main__":
    main()
