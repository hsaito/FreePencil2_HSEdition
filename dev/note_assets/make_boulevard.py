"""並木道の大通り: v2.7 相当(精密)と v2.8 の手描き背景の比較が映える場面。

精密では葉の木が黒い塊になり、手描き背景では葉がほどける(町と記事の画像で確認済みの差)。
その木を、歩道 2 列 x 両側 + 中央分離帯 1 列で、奥まで並べる。ビルは大通り(make_avenue)
と同じ低い密度(どちらの仕上がりでもくっきり描ける)にして、遠景は並木と空で抜ける。

  blender -b --factory-startup --python make_boulevard.py -- --wire [--res 1600]          構図の確認(数秒)
  blender -b --factory-startup --python make_boulevard.py -- --pre-only [--out out/boulevard]   STEP0 前の .blend
木もビルも町と同じ灰色の材質にする(線の有無だけを比べる)。
"""
from __future__ import annotations

import glob
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


if "--out" not in ARGV:          # make_avenue の既定の出力先を使わない
    sys.argv += ["--out", str(HERE / "out" / "boulevard")]
PARK = float(arg("--park", "0"))       # 中央の並木公園の半幅(0 = 公園なし、分離帯 1 列)
if "--rw" not in ARGV:
    sys.argv += ["--rw", str(PARK + 11.0 if PARK > 0 else 14.0)]
if "--y1" not in ARGV:
    sys.argv += ["--y1", "1600"]

import bpy                     # noqa: E402
import fp_batch                # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402
import make_avenue as av       # noqa: E402

TREE = arg("--tree", "european-maple")
TREE_H = float(arg("--tree-h", "9.0"))
SPACING = float(arg("--spacing", "11.0"))
SIDEWALK_ROWS = (2.2, 5.6)        # 縁石からの距離(歩道の 2 列)


def say(m):
    print(f"@@@ {m}", flush=True)


def load_tree():
    return load_asset(TREE, TREE_H, "tree_src")


def load_asset(pattern, height, name):
    """BlenderKit のアセットを 1 枚のメッシュに焼き、高さをそろえ、足元の中心を原点にする。原本は写さない。"""
    root = Path.home() / "blenderkit_data" / "models"
    hits = sorted(glob.glob(str(root / f"{pattern}*" / "*.blend")))
    if not hits:
        raise RuntimeError(f"見つからない: {pattern}")
    meshes, others = fp_batch.append_objects(Path(hits[0]))
    meshes = [o for o in meshes if not o.hide_render]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.join()
    t = bpy.context.object
    t.parent = None
    t.constraints.clear()
    for o in others:
        if o.name in bpy.data.objects and o is not t:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()
    pts = [t.matrix_world @ Vector(c) for c in t.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    s = height / max(hi.z - lo.z, 1e-6)
    cx, cy = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2
    t.data.transform(Matrix.Scale(s, 4) @ Matrix.Translation(Vector((-cx, -cy, -lo.z))))
    t.matrix_world = Matrix.Identity(4)
    t.name = name
    t.hide_render = True
    t.hide_viewport = True
    say(f"{pattern}: {len(t.data.polygons):,} 面、高さ {height} m")
    return t


CARS = (("police-car", 1.5), ("nypd_toyota", 1.5), ("lancia-delta", 1.45),
        ("hyundai-veloster", 1.4), ("audi_r8", 1.25), ("mclaren_720s", 1.2))


def cars(rng):
    """車の列。各車に初期位置 fp_y0 と 1 コマの移動量 fp_v(m)を持たせ、撮影側で動かす。
    アセットの正面は -y(町の実測)。北向き(+y)は 180 度回す。左側通行: 北向きは x<0。"""
    srcs = [load_asset(p, h, f"car_src_{p}") for p, h in CARS]
    a, b = (PARK + 3.0, PARK + 8.0) if PARK > 0 else (4.6, 10.2)
    lanes = ((-a, +1, 0.95, 1.35), (-b, +1, 0.75, 1.05),     # 北向き(カメラと同じ向き): 追い越していく
             (a, -1, 0.85, 1.15), (b, -1, 0.75, 1.0))         # 南向き: すれ違う
    made = []
    for x, dirn, vmin, vmax in lanes:
        y = av.Y0 + rng.uniform(0, 20)
        v = rng.uniform(vmin, vmax) * dirn
        while y < av.Y1:
            c = rng.choice(srcs).copy()
            bpy.context.scene.collection.objects.link(c)
            c.matrix_world = (Matrix.Translation(Vector((x, y, 0.0)))
                              @ Matrix.Rotation(math.pi if dirn > 0 else 0.0, 4, "Z"))
            c["fp_y0"] = y
            c["fp_v"] = v
            c.hide_render = False
            c.hide_viewport = False
            made.append(c)
            y += rng.uniform(22, 48)
    say(f"車 {len(made)} 台")
    return made


def plant(src, rng):
    made = []
    xs = []
    for sx in (-1, 1):
        for d in SIDEWALK_ROWS:
            xs.append(sx * (av.RW + d))
    if PARK > 0:                                     # 公園の中の並木(4.5m おき)
        x = -PARK + 2.5
        while x < PARK - 2.0:
            xs.append(x)
            x += 4.5
    else:
        xs.append(0.0)                               # 中央分離帯
    for x in xs:
        y = av.Y0 + rng.uniform(0, SPACING)
        while y < av.Y1:
            c = src.copy()
            bpy.context.scene.collection.objects.link(c)
            sc_ = rng.uniform(0.85, 1.15)
            c.matrix_world = (Matrix.Translation(Vector((x + rng.uniform(-0.3, 0.3), y, 0)))
                              @ Matrix.Rotation(rng.uniform(0, math.tau), 4, "Z") @ Matrix.Scale(sc_, 4))
            c.hide_render = False
            c.hide_viewport = False
            made.append(c)
            y += SPACING * rng.uniform(0.9, 1.1)
    say(f"木 {len(made)} 本")
    return made


def median():
    mb = av.MB("median")
    w = 2 * PARK if PARK > 0 else 3.2
    mb.box(0, (av.Y0 + av.Y1) / 2, 0.15, w, av.Y1 - av.Y0 + 400, 0.3)
    if PARK > 0:                                         # 公園の中の遊歩道(縦に 2 本)
        for sx in (-1, 1):
            mb.box(sx * PARK * 0.45, (av.Y0 + av.Y1) / 2, 0.32, 1.6, av.Y1 - av.Y0 + 400, 0.04)
    return mb.build()


PLANES = [tuple(float(v) for v in spec.split(":")) for spec in arg("--planes", "").split(",") if spec]
# 1 機ずつ「y0:z0:x:v:vz」(初期位置 y・高さ・横位置・1 コマの前進量・1 コマの高さの変化)


def planes():
    """飛行機(A320)。機首を +y に向け、実寸(全長 約 38m)にする。撮影側で fp_y0/fp_v/fp_z0/fp_vz で動かす。"""
    if not PLANES:
        return []
    src = load_asset("airbus_a320", 6.0, "plane_src")       # 高さ 6 で全長 約 38m(読み込み時の実測)
    made = []
    for y0, z0, x, v, vz in PLANES:
        c = src.copy()
        bpy.context.scene.collection.objects.link(c)
        c.matrix_world = (Matrix.Translation(Vector((x, y0, z0)))
                          @ Matrix.Rotation(math.radians(-90), 4, "Z")
                          @ Matrix.Rotation(math.radians(-4.0 if vz < 0 else 3.0), 4, "Y"))
        c["fp_y0"] = y0
        c["fp_v"] = v
        c["fp_z0"] = z0
        c["fp_vz"] = vz
        c.hide_render = False
        c.hide_viewport = False
        made.append(c)
    say(f"飛行機 {len(made)} 機")
    return made


def main():
    av.OUT.mkdir(parents=True, exist_ok=True)
    sc, objs, ground = av.build_scene()
    rng = random.Random(av.SEED + 100)
    src = load_tree()
    trees = plant(src, rng)
    med = median()
    car_list = cars(rng) if "--no-cars" not in ARGV else []
    plane_list = planes()
    av.grey(trees + [med] + car_list + plane_list)
    objs = objs + trees + [med] + car_list + plane_list
    sc.render.resolution_x = av.RES
    sc.render.resolution_y = av.RES * 9 // 16
    sc.render.image_settings.file_format = "PNG"
    if "--wire" in ARGV:
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "FLAT"
        sh.color_type = "SINGLE"
        sh.single_color = (0.93, 0.93, 0.93)
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.show_object_outline = True
        sc.render.film_transparent = False
        sc.render.filepath = str(av.OUT / f"{arg('--name', 'wire')}.png")
        bpy.ops.render.render(write_still=True)
        say("wire done")
        return
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
    bpy.ops.wm.save_as_mainfile(filepath=str(av.OUT / "boulevard_pre.blend"))
    faces = sum(len(o.data.polygons) for o in sc.objects if o.type == "MESH" and not o.hide_render)
    say(f"saved pre / 面(複製込み) {faces:,}")


main()
