"""「並べただけ」ではない町を組む。通り・歩道・街区・街灯・電柱・車・人。

BlenderKit の建物は 2 種(家・アパート)しか無いので、街区の建物は
手続きで作る(箱 + 窓 + 入口 + 屋上の手すり)。線画は形しか見ないので
テクスチャは要らない。木・車・人・ベンチはアセットのリンク複製
(メッシュ共有 = STEP1 は 1 回塗れば済む)。

  blender -b --factory-startup --python make_real_town.py -- \
      [--out out/real_town] [--style BACKGROUND] [--seed 3]

出すもの: town.blend(STEP0 済み、カメラ付き)。絵は preview_shot.py で
GUI の Blender を開いてビューポートのプレビューを撮る(レンダしない)。
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
OUT = Path(arg("--out", str(HERE / "out" / "real_town"))).resolve()
STYLE = arg("--style", "BACKGROUND")
SEED = int(arg("--seed", "3"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", "1920", "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_town_demo as td       # noqa: E402  (load_lot / bounds / transform)
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()
RNG = random.Random(SEED)

# 通り: 大通りが y 方向(x = -6..6)、横町が y = 0 と y = 60(幅 12)。
# 歩道 3m、街区はその外
ROAD = 6.0          # 車道の半幅
WALK = 3.0          # 歩道の幅
CURB = ROAD + WALK  # 街区の始まり(±9)
CROSS = (0.0, 60.0)     # 横町の中心 y
BLOCK_Y = ((9.0, 51.0), (69.0, 120.0), (-60.0, -9.0))   # 街区の y 範囲
BLOCK_X = ((9.0, 60.0), (-60.0, -9.0))                   # 街区の x 範囲


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# ---------------------------------------------------------------- 手続きの部品

def box(name, cx, cy, cz, sx, sy, sz, rot_z=0.0):
    """中心と大きさで直方体を置く。"""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, cz))
    o = bpy.context.object
    o.name = name
    o.scale = (sx, sy, sz)
    o.rotation_euler = (0.0, 0.0, rot_z)
    return o


def cylinder(name, cx, cy, cz, r, h, verts=12):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h,
                                        location=(cx, cy, cz))
    o = bpy.context.object
    o.name = name
    return o


def building(cx, cy, w, d, h, face, rng, idx):
    """箱の建物。face は通りに向く側 ('-x' '+x' '-y' '+y')。窓は正面と側面。"""
    made = []
    made.append(box(f"bld{idx}", cx, cy, h / 2, w, d, h))
    # 屋上の手すり(少し大きい薄い枠)
    made.append(box(f"bld{idx}_parapet", cx, cy, h + 0.15, w + 0.3, d + 0.3, 0.3))
    floors = max(1, int(h // 3.2))
    win_h = 1.4
    win_w = rng.choice((1.0, 1.2, 1.6))
    gap = win_w * rng.choice((0.8, 1.0, 1.4))
    for side in ("-x", "+x", "-y", "+y"):
        if side not in (face,) and rng.random() < 0.4:
            continue
        along = w if side in ("-y", "+y") else d
        n = max(1, int((along - 1.0) // (win_w + gap)))
        span = n * win_w + (n - 1) * gap
        for fl in range(floors):
            z = 1.0 + fl * 3.2 + win_h / 2
            for k in range(n):
                t = -span / 2 + k * (win_w + gap) + win_w / 2
                # 1階の正面の真ん中は入口
                door = fl == 0 and side == face and k == n // 2
                ww, hh, zz = (1.4, 2.4, 1.2) if door else (win_w, win_h, z)
                if side == "-y":
                    made.append(box(f"bld{idx}_w", cx + t, cy - d / 2 - 0.06, zz, ww, 0.12, hh))
                elif side == "+y":
                    made.append(box(f"bld{idx}_w", cx + t, cy + d / 2 + 0.06, zz, ww, 0.12, hh))
                elif side == "-x":
                    made.append(box(f"bld{idx}_w", cx - w / 2 - 0.06, cy + t, zz, 0.12, ww, hh))
                else:
                    made.append(box(f"bld{idx}_w", cx + w / 2 + 0.06, cy + t, zz, 0.12, ww, hh))
    # 1階に庇(ひさし)を付けることがある
    if rng.random() < 0.5:
        if face == "-x":
            made.append(box(f"bld{idx}_awn", cx - w / 2 - 0.6, cy, 3.1, 1.2, min(w, d) * 0.6, 0.12))
        elif face == "+x":
            made.append(box(f"bld{idx}_awn", cx + w / 2 + 0.6, cy, 3.1, 1.2, min(w, d) * 0.6, 0.12))
        elif face == "-y":
            made.append(box(f"bld{idx}_awn", cx, cy - d / 2 - 0.6, 3.1, min(w, d) * 0.6, 1.2, 0.12))
        else:
            made.append(box(f"bld{idx}_awn", cx, cy + d / 2 + 0.6, 3.1, min(w, d) * 0.6, 1.2, 0.12))
    return made


def lamp(x, y, idx):
    made = [cylinder(f"lamp{idx}", x, y, 2.6, 0.07, 5.2, 8)]
    made.append(box(f"lamp{idx}_head", x + (0.6 if x < 0 else -0.6), y, 5.2, 1.2, 0.25, 0.18))
    return made


def pole(x, y, idx):
    made = [cylinder(f"pole{idx}", x, y, 4.5, 0.12, 9.0, 8)]
    made.append(box(f"pole{idx}_arm", x, y, 8.6, 0.12, 2.0, 0.12))
    return made


def street_furniture():
    made = []
    # 縁石(歩道の段差)
    for sx in (-1, 1):
        for y0, y1 in ((-60, -6), (6, 54), (66, 130)):
            made.append(box("curb", sx * (ROAD + 0.1), (y0 + y1) / 2, 0.08, 0.2, y1 - y0, 0.16))
            made.append(box("walk", sx * (ROAD + WALK / 2 + 0.1), (y0 + y1) / 2, 0.06, WALK - 0.2, y1 - y0, 0.12))
    for cy in CROSS:
        for sy in (-1, 1):
            for x0, x1 in ((-60, -6), (6, 60)):
                made.append(box("curb", (x0 + x1) / 2, cy + sy * (ROAD + 0.1), 0.08, x1 - x0, 0.2, 0.16))
                made.append(box("walk", (x0 + x1) / 2, cy + sy * (ROAD + WALK / 2 + 0.1), 0.06, x1 - x0, WALK - 0.2, 0.12))
    # 車線の中央線(破線)と横断歩道
    for y in range(-56, 128, 6):
        if any(abs(y - c) < ROAD + 2 for c in CROSS):
            continue
        made.append(box("lane", 0.0, y + 1.5, 0.005, 0.15, 3.0, 0.01))
    for cy in CROSS:
        for sy in (-1, 1):
            for k in range(-4, 5):
                made.append(box("zebra", k * 1.2, cy + sy * (ROAD - 1.6), 0.005, 0.6, 2.6, 0.01))
        for sx in (-1, 1):
            for k in range(-4, 5):
                made.append(box("zebra", sx * (ROAD - 1.6), cy + k * 1.2, 0.005, 2.6, 0.6, 0.01))
    # 街灯と電柱
    i = 0
    for y in range(-50, 126, 16):
        if any(abs(y - c) < 8 for c in CROSS):
            continue
        made += lamp(-(ROAD + 0.8), y, i)
        made += pole(ROAD + 1.0, y + 8, i)
        i += 1
    return made


def blocks(rng):
    """街区の縁に建物を並べる。通りに面した側を正面にする。"""
    made = []
    idx = 0
    for (x0, x1) in BLOCK_X:
        for (y0, y1) in BLOCK_Y:
            # 大通りに面した列(x が街区の内側の端)
            y = y0 + 1.0
            while y < y1 - 6.0:
                w = rng.uniform(9.0, 16.0)
                d = rng.uniform(8.0, 14.0)
                if y + w > y1 - 1.0:
                    w = y1 - 1.0 - y
                    if w < 6.0:
                        break
                h = rng.choice((3.5, 6.5, 6.5, 9.7, 9.7, 12.9, 16.1))
                if x1 < 0:
                    cx, face = x1 - d / 2, "+x"
                else:
                    cx, face = x0 + d / 2, "-x"
                made += building(cx, y + w / 2, d, w, h, face, rng, idx)
                idx += 1
                y += w + rng.uniform(0.6, 2.5)
            # 横町に面した列(街区の y の端)。奥は大通り列と重ならない x から
            for cy_edge, face in ((y0, "-y"), (y1, "+y")):
                if not any(abs(cy_edge - c) < 12 for c in CROSS):
                    continue
                x = (x0 + 16.0) if x0 > 0 else (x0 + 1.0)
                xe = (x1 - 1.0) if x0 > 0 else (x1 - 16.0)
                while x < xe - 6.0:
                    w = rng.uniform(9.0, 15.0)
                    d = rng.uniform(8.0, 12.0)
                    if x + w > xe:
                        w = xe - x
                        if w < 6.0:
                            break
                    h = rng.choice((3.5, 6.5, 9.7, 9.7, 12.9))
                    cy = cy_edge + (d / 2 if face == "-y" else -d / 2)
                    made += building(x + w / 2, cy, w, d, h, face, rng, idx)
                    idx += 1
                    x += w + rng.uniform(0.6, 2.5)
    return made


# ---------------------------------------------------------------- アセット

def place_asset(objs, x, y, rot_deg, height):
    bb = td.bounds(objs)
    size = bb[1] - bb[0]
    s = height / max(size.z, 1e-6)
    td.transform(objs, Matrix.Scale(s, 4))
    bb = td.bounds(objs)
    td.transform(objs, Matrix.Translation(Vector((-(bb[0].x + bb[1].x) / 2,
                                                  -(bb[0].y + bb[1].y) / 2, -bb[0].z))))
    td.transform(objs, Matrix.Translation(Vector((x, y, 0))) @ Matrix.Rotation(math.radians(rot_deg), 4, "Z"))


def duplicate(objs, x, y, rot_deg, scale=1.0):
    """リンク複製(メッシュ共有)。元の配置からの相対で置く。"""
    base = Vector((1000.0, 1000.0, 0.0))     # 原本は place_asset でここに置く
    new = []
    for o in objs:
        c = o.copy()
        bpy.context.scene.collection.objects.link(c)
        new.append(c)
    group = set(objs)
    for o, c in zip(objs, new):
        if o.parent in group:
            c.parent = new[objs.index(o.parent)]
        # モディファイアが参照する物(アーマチュア、ミラーの基準など)も
        # 複製側へ。元のままだとミラーが 2000m 先に写った(実測)
        for md in c.modifiers:
            for prop in md.bl_rna.properties:
                if prop.type != "POINTER" or prop.fixed_type is None:
                    continue
                if prop.fixed_type.identifier != "Object":
                    continue
                tgt = getattr(md, prop.identifier, None)
                if tgt in group:
                    setattr(md, prop.identifier, new[objs.index(tgt)])
    m = (Matrix.Translation(Vector((x, y, 0))) @ Matrix.Rotation(math.radians(rot_deg), 4, "Z")
         @ Matrix.Scale(scale, 4) @ Matrix.Translation(-base))
    for c in new:
        if c.parent in new:
            continue
        c.matrix_world = m @ c.matrix_world
    bpy.context.view_layer.update()
    return new


def assets(rng):
    made = []
    lib = {}
    for pat, height in (("european-maple", 7.0), ("tree_autumn", 8.0),
                        ("modern-house", 6.5), ("japan-apartment", 14.0),
                        ("police-car", 1.5), ("nypd_toyota", 1.5), ("lancia-delta", 1.45),
                        ("hyundai-veloster", 1.4), ("audi_r8", 1.25),
                        ("man_01", 1.75), ("standing-cool-bald", 1.8), ("stylized-male", 1.75),
                        ("anime-girl", 1.6), ("manchester-acacia", 0.8), ("trash_can", 1.0)):
        objs = td.load_lot(pat)
        if not objs:
            say(f"見つからない: {pat}")
            continue
        place_asset(objs, 1000.0, 1000.0, 0.0, height)     # 原本は遠くへ
        lib[pat] = objs
        made += [o for o in objs if o.type == "MESH" and not o.hide_render]
    # 原本は写らないよう非表示(複製だけ写す)
    for objs in lib.values():
        for o in objs:
            o.hide_render = True
            o.hide_viewport = True

    def put(pat, x, y, rot, scale=1.0):
        if pat not in lib:
            return
        new = duplicate(lib[pat], x, y, rot, scale)
        for c in new:
            c.hide_render = False
            c.hide_viewport = False
        made.extend(o for o in new if o.type == "MESH")

    # アセットの建物: 街区の角に
    put("japan-apartment", -CURB - 9.0, 9.0 + 9.0, 90)
    put("japan-apartment", CURB + 9.0, 69.0 + 9.0, -90)
    put("modern-house", CURB + 7.0, -9.0 - 8.0, -90)
    put("modern-house", -CURB - 7.0, 69.0 + 7.0, 90)
    # 街路樹: 歩道の外寄り、12m ごと(街灯とずらす)
    for y in range(-46, 126, 12):
        if any(abs(y - c) < 9 for c in CROSS):
            continue
        for sx in (-1, 1):
            pat = "european-maple" if (y // 12 + sx) % 3 else "tree_autumn"
            put(pat, sx * (ROAD + 2.2), y + rng.uniform(-1.0, 1.0), rng.uniform(0, 360),
                rng.uniform(0.85, 1.15))
    # 車: 車線に沿って。右側通行、間隔はばらす
    cars = ["police-car", "nypd_toyota", "lancia-delta", "hyundai-veloster", "audi_r8"]
    y = -40.0
    while y < 118:
        put(rng.choice(cars), 3.0, y, 0)
        y += rng.uniform(14, 30)
    y = -30.0
    while y < 118:
        put(rng.choice(cars), -3.0, y, 180)
        y += rng.uniform(16, 34)
    # 横町にも
    for cy in CROSS:
        for x in (-30.0, 22.0):
            put(rng.choice(cars), x, cy + 3.0, 90)
    # 人: 歩道に
    people = ["man_01", "standing-cool-bald", "stylized-male", "anime-girl"]
    for _ in range(14):
        sx = rng.choice((-1, 1))
        y = rng.uniform(-40, 115)
        if any(abs(y - c) < 7 for c in CROSS):
            continue
        put(rng.choice(people), sx * (ROAD + rng.uniform(0.6, 2.4)), y, rng.uniform(0, 360))
    # ベンチとゴミ箱
    for y in (20.0, 44.0, 84.0, 104.0):
        put("manchester-acacia", -(ROAD + 2.3), y + 5.0, 90)
        put("trash_can", ROAD + 1.4, y + 2.0, 0)
    return made


# ---------------------------------------------------------------- 全体

def stage(length=130.0):
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=1)
    ground = bpy.context.object
    ground.scale = (4000, 4000, 1)
    ground.location = (0, 30, -0.02)
    ground.name = "FP_ground"
    cd = bpy.data.cameras.new("C")
    cd.lens = 28.0
    cd.clip_end = 6000
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (-2.0, -34.0, 1.7)
    cam.rotation_euler = (math.radians(88.0), 0.0, math.radians(-4.0))
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
    rng = RNG
    meshes = []
    meshes += blocks(rng)
    say(f"建物 {len(meshes)} 個(部品込み)")
    meshes += street_furniture()
    meshes += assets(rng)
    say(f"メッシュ {len(meshes)} 個")
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
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    say(f"STEP0 done: 距離 {sc.fp_lw_far_start:.1f}..{sc.fp_lw_far_end:.1f} 密度 {sc.fp_lw_density:.3f}")
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = 'MONO_LIGHT'
    # プレビュー用: ビューポートのコンポジタを常時に
    sc.fp_enable_compositor_view = True
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "town.blend"))
    say(f"保存 {OUT / 'town.blend'}")


if __name__ == "__main__":
    main()
