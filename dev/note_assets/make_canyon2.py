"""超高層の峡谷 v2: 窓の種類・セットバック・屋上を作り込んだ版(背景の密度のデモ用)。

  blender -b --factory-startup --python make_canyon2.py -- --beauty [--res 1280] [--seed 7] [--out out/canyon2]
      陰影だけの絵を撮る(STEP0 なし。構図と高層の変化の確認用、数秒)
  blender -b --factory-startup --python make_canyon2.py -- --build [--seed 7] [--out out/canyon2]
      STEP0 前の .blend(canyon2_pre.blend)を作る

参考は AKIRA の大通り: 一点透視、両側に超高層、窓の格子がびっしり、遠くは空へ抜ける。
窓の種類は 4 つ(縦の方立・窓の格子・横の帯窓・リブ)を建物ごとに変え、
段ごとに種類も変える。屋上は階段状の冠と尖塔。
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
OUT = Path(arg("--out", str(HERE / "out" / "canyon2"))).resolve()
RES = int(arg("--res", "1280"))
SEED = int(arg("--seed", "7"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))

import bpy          # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402

from town_kit import MB, facade_matrix   # noqa: E402

RW = float(arg("--rw", "17"))        # 通りの半幅
Y0, Y1 = float(arg("--y0", "-420")), 700.0      # 建物の並びの手前の端と奥の端
CAM = (0.0, float(arg("--cam-y", "-60")), float(arg("--cam-z", "2.4")))
LENS = float(arg("--lens", "26"))


def say(m):
    print(f"@@@ {m}", flush=True)


# ---------------------------------------------------------------- 窓の種類(ローカル: 正面 y=0、外が -y)

def deco_fins(mb, W, h, fh, rng):
    """縦の方立(リブ): 細かい縦縞 + 階ごとの無目とスパンドレル。"""
    pitch = rng.choice((0.35, 0.45, 0.6, 0.75))
    k = max(2, int(W / pitch))
    for i in range(k + 1):
        mb.box(-W / 2 + i * W / k, -0.10, h / 2, 0.09, 0.2, h)
    every = rng.choice((3, 4, 6))
    for fl in range(every, int(h / fh), every):
        mb.box(0, -0.2, fl * fh, W, 0.4, 0.45)             # リブより手前に出る帯


def deco_punched(mb, W, h, fh, rng):
    """窓の格子: 小さな窓の箱が、階 x 列にびっしり。"""
    pitch = rng.choice((0.9, 1.1, 1.4))
    ww = pitch * rng.uniform(0.5, 0.65)
    wh = fh * rng.uniform(0.4, 0.55)
    ncol = max(2, int(W / pitch))
    for fl in range(int(h / fh)):
        z = fl * fh + fh * 0.5
        for c in range(ncol):
            if rng.random() < 0.03:
                continue
            mb.box(-W / 2 + (c + 0.5) * W / ncol, -0.06, z, ww, 0.12, wh)


def deco_band(mb, W, h, fh, rng):
    """横の帯窓: 階ごとに横長の窓 + 所々の縦の仕切り。"""
    div = rng.choice((3.0, 4.5, 6.0))
    wh = fh * rng.uniform(0.5, 0.65)
    for fl in range(int(h / fh)):
        z = fl * fh + fh * 0.5
        mb.box(0, -0.05, z, W, 0.1, wh)
    k = max(1, int(W / div))
    for i in range(k + 1):
        mb.box(-W / 2 + i * W / k, -0.09, h / 2, 0.18, 0.18, h)


def deco_grid(mb, W, h, fh, rng):
    """大きな格子: 太い縦横の枠の中に、細かい方立。"""
    bay = rng.choice((3.0, 4.0, 6.0))
    k = max(1, int(W / bay))
    for i in range(k + 1):
        mb.box(-W / 2 + i * W / k, -0.14, h / 2, 0.25, 0.28, h)
    per = rng.choice((2, 3))
    for fl in range(int(h / fh)):
        z = fl * fh
        if fl % per == 0:
            mb.box(0, -0.12, z, W, 0.24, 0.22)
    sub = max(2, int(bay / 0.55))
    for i in range(k):
        x0 = -W / 2 + i * W / k
        for j in range(1, sub):
            mb.box(x0 + j * W / k / sub, -0.05, h / 2, 0.05, 0.1, h)


STYLES = (deco_fins, deco_punched, deco_band, deco_grid)


def crown(mb, W, D, h, rng):
    """屋上: 階段状の冠と、ときどき尖塔。"""
    z = h
    mb.box(0, D / 2, z + 0.4, W + 0.4, D + 0.4, 0.8)
    z += 0.8
    for t in range(rng.randint(1, 3)):
        s = 0.78 - 0.17 * t
        th = rng.uniform(2.5, 6.0)
        mb.box(0, D / 2, z + th / 2, W * s, D * s, th)
        k = max(2, int(W * s / 1.2))
        for i in range(k + 1):
            mb.box(-W * s / 2 + i * W * s / k, D / 2 - D * s / 2 - 0.05, z + th / 2, 0.08, 0.1, th)
        z += th
    if rng.random() < 0.55:
        sh = rng.uniform(8, 26)
        mb.box(0, D / 2, z + sh / 2, 0.5, 0.5, sh)
        for zz in np.linspace(z + sh * 0.3, z + sh * 0.9, 4):
            mb.box(0, D / 2, zz, 2.2, 0.06, 0.06)


def skyscraper(cx, cy, w, d, h, face, rng, idx, style=None, ledges=True):
    """w = 通りに直角の長さ(奥行き)、d = 通りに沿った長さ。呼び方は town_kit_more.tower と同じ。"""
    mat, along, depth = facade_matrix(cx, cy, w, d, face)
    mb = MB(f"sky{idx}")
    fh = rng.choice((3.0, 3.3, 3.6))
    style = style or rng.choice(STYLES)
    mb.box(0, depth / 2, h / 2, along, depth, h)
    R = mat.to_3x3()
    for side in range(4):
        W = along if side % 2 == 0 else depth
        D = depth if side % 2 == 0 else along
        n_local = Matrix.Rotation(side * math.pi / 2, 3, "Z") @ Vector((0, -1, 0))
        n_world = R @ n_local
        if not (side == 0 or n_world.y < -0.5):      # 正面と、手前(-y)を向く面だけ細かく
            continue
        mb.push(np.array(Matrix.Translation((0, depth / 2, 0))
                         @ Matrix.Rotation(side * math.pi / 2, 4, "Z")
                         @ Matrix.Translation((0, -D / 2, 0))))
        style(mb, W, h, fh, rng)
        for s in (-1, 1):
            mb.box(s * W / 2, -0.15, h / 2, 0.5, 0.3, h)                 # 角の柱
        if ledges:
            step = rng.choice((8, 12, 16)) * fh
            z = step
            while z < h - 6:
                mb.box(0, -0.3, z, W + 0.4, 0.6, 0.5)                    # 張り出しの庇
                z += step
        mb.pop()
    crown(mb, along, depth, h, rng)
    return mb.build(mat)


# ---------------------------------------------------------------- 並べる

def layout(rng):
    objs = []
    idx = 0
    for sx in (-1, 1):
        face = "-x" if sx > 0 else "+x"
        y = Y0 + rng.uniform(0, 8)
        while y < Y1:
            along = rng.uniform(13, 30)
            depth = rng.uniform(20, 34)
            cy = y + along / 2
            dist = max(0.0, y)
            # 奥へ行くほど高くする(遠くでも空へ抜けず、壁が続く)
            hb = rng.uniform(22, 44)
            objs.append(skyscraper(sx * (RW + depth / 2), cy, depth, along, hb, face, rng, idx,
                                   ledges=False))
            idx += 1
            tiers = rng.choice((1, 1, 2))
            top = hb
            dd, aa, off = depth, along, 0.0
            for t in range(tiers):
                sb = rng.uniform(2.0, 6.0)
                dd *= rng.uniform(0.6, 0.85)
                aa *= rng.uniform(0.65, 0.95)
                off += sb
                ht = rng.uniform(70, 160) + dist * 0.08 + t * rng.uniform(25, 60)
                objs.append(skyscraper(sx * (RW + off + dd / 2), cy + rng.uniform(-1.0, 1.0),
                                       dd, aa, ht, face, rng, idx))
                idx += 1
            y += along + rng.uniform(0.0, 2.0)
    return [o for o in objs if o is not None]


def street_marks():
    """中央線の破線と縁石: 消失点へ集まる線(遠近の手がかり)。"""
    mb = MB("street")
    for sx in (-1, 1):
        mb.box(sx * (RW - 0.15), (Y0 + Y1) / 2 - 50, 0.12, 0.3, Y1 - Y0 + 400, 0.24)
    return mb.build()


def stage(res):
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=1)
    ground = bpy.context.object
    ground.scale = (4000, 4000, 1)
    ground.location = (0, 200, -0.02)
    ground.name = "FP_ground"
    cd = bpy.data.cameras.new("C")
    cd.lens = LENS
    cd.shift_y = float(arg("--shift-y", "0.18"))      # 見上げても垂直線が立つように、画面を上へずらす
    cd.clip_start = 0.3
    cd.clip_end = 3000
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = CAM
    cam.rotation_euler = (math.radians(90.0 + float(arg("--tilt", "0.0"))), 0.0, 0.0)
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.75, 0.75, 0.77, 1)
        bg.inputs[1].default_value = float(arg("--ambient", "0.7"))
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = math.radians(2.0)
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(float(arg("--sun-el", "52"))), 0, math.radians(float(arg("--sun-az", "22"))))
    return ground


def grey(objs):
    m = bpy.data.materials.new("canyon_grey")
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (0.78, 0.78, 0.78, 1)
        b.inputs["Roughness"].default_value = 0.9
    for o in objs:
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(m)


def build_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
    rng = random.Random(SEED)
    towers = layout(rng)
    marks = street_marks()
    ground = stage(RES)
    allobj = towers + [marks, ground]
    grey(allobj)
    sc = bpy.context.scene
    from_fp = [o for o in towers + [marks]]
    sc.render.engine = "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 2, 0) else "BLENDER_EEVEE"
    faces = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    say(f"高層 {len(towers)} 棟 / 面 {faces:,}")
    return sc, from_fp, ground


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sc, objs, ground = build_scene()
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.render.image_settings.file_format = "PNG"
    if "--wire" in ARGV:          # 形の確認用: Workbench の凹凸強調(STEP0 の線とは別物)
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "FLAT"
        sh.color_type = "SINGLE"
        sh.single_color = (0.93, 0.93, 0.93)
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.cavity_ridge_factor = 1.6
        sh.cavity_valley_factor = 1.6
        sh.curvature_ridge_factor = 1.0
        sh.show_object_outline = True
        sc.render.film_transparent = False
        sc.render.filepath = str(OUT / "wire.png")
        bpy.ops.render.render(write_still=True)
        say("wire done")
        return
    if "--beauty" in ARGV:
        sc.eevee.taa_render_samples = 16
        sc.render.film_transparent = False
        sc.render.filepath = str(OUT / "beauty.png")
        bpy.ops.render.render(write_still=True)
        say("beauty done")
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
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs + [ground]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "canyon2_pre.blend"))
    say("saved pre")
    if "--full" not in ARGV:
        return
    SAMPLES = int(arg("--samples", "8"))
    sc.eevee.taa_render_samples = SAMPLES

    def shot(name):
        sc.render.filepath = str(OUT / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        say(f"rendered {name}")

    sc.fp_auto_style = "BACKGROUND"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    say(f"STEP0 奥 {sc.fp_lw_far_start:.1f}..{sc.fp_lw_far_end:.1f} 密度 {sc.fp_lw_density:.3f}")
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = "MONO_LIGHT"
    sc.fp_lw_far_amount = 0.0        # 奥の扱いは使わない(つぶれ軽減と重ねると遠景がにじむ)
    sc.fp_lw_relief = 1.0
    shot("bg_on")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "canyon2_bg.blend"))
    sc.fp_preview_mode = "WHITE"
    shot("bg_on_white")
    sc.fp_preview_mode = "MONO_LIGHT"
    sc.fp_lw_relief = 0.0
    shot("bg_off")
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "canyon2_pre.blend"))
    sc = bpy.context.scene
    sc.eevee.taa_render_samples = SAMPLES
    sc.fp_auto_style = "PRECISE"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = "MONO_LIGHT"
    shot("precise")
    say("done")


main()
