"""たくさんのモデルを町のように並べ、カメラが通りを進むデモを撮る。

仕上がりは「強弱(手描き)」。白マテリアルではなくモノ光プレビュー
(ディフューズ直接光のグレースケール)を薄く敷いて、線画に薄い陰影を
乗せる。強弱・14度・稜線・しきい値の計測はすべて STEP0 に任せる。

配置:
    通り(y 方向)の両側に、建物・乗り物・人・小物を大小ばらばらに置く。
    地面は大きな平面(白マテリアル、線は出ない)。カメラは通りの上を
    前に進みながら、ゆっくり左右を見る。

  blender -b --factory-startup --python make_town_demo.py -- \
      [--frames 240] [--res 1920] [--floor 0.55] [--style BACKGROUND] [--gap 0] [--ink 0.75] [--soften 2]

--style は STEP0 の仕上がり(WEIGHTED = キャラ / BACKGROUND = 手描き背景)。
手描き背景は奥の扱い(細く・少なく・薄く)と葉の房まとめを STEP0 が入れる。
--gap は葉の隙間埋め(px、既定 0)。
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
OUT = Path(arg("--out", str(HERE / "out" / "town"))).resolve()
RES_W = int(arg("--res", "1920"))
RES_H = RES_W * 9 // 16
FRAMES = int(arg("--frames", "240"))
MONO_FLOOR = float(arg("--floor", "0.55"))     # 影の下限。高いほど薄い陰影
START = int(arg("--start", "0"))
STYLE = arg("--style", "WEIGHTED")
GAP = int(arg("--gap", "0"))
INK = float(arg("--ink", "1.0"))        # 線の濃さ(表示)。0.75 で濃い灰色
SOFTEN = float(arg("--soften", "2.0"))  # 縁のぼかし px(200%)

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()

# (名前の一部, 目標の高さ, 通りのどちら側か 'L'/'R'/'C'(中央))
# 高さはだいたいの実物感。人 1.7、車 1.5、家 6、木 5、小物は台の上
LOTS = [
    ("modern-house", 6.5, "L"), ("japan-apartment", 14.0, "R"),
    ("tree_autumn", 5.5, "L"), ("coconut-tree", 6.0, "R"),
    ("police-car", 1.5, "C"), ("nypd_toyota", 1.5, "C"),
    ("lancia-delta", 1.45, "C"), ("low-poly-car", 1.4, "C"),
    ("man_01", 1.75, "L"), ("standing-cool-bald", 1.8, "R"),
    ("anime-girl", 1.6, "L"), ("stylized-male", 1.75, "R"),
    ("trash_can", 1.0, "L"), ("school-locker", 1.9, "R"),
    ("simple-wooden-chair", 0.9, "L"), ("manchester-acacia", 0.8, "R"),
    ("mercedes-benze", 1.4, "C"), ("door-classic", 2.2, "L"),
    ("kaino-school", 4.5, "R"), ("robot-kuka", 2.5, "L"),
    ("eiffel_tower", 3.0, "L"), ("portable-generator", 0.9, "R"),
    ("fridge-midea", 1.8, "L"), ("kallax-ikea", 1.5, "R"),
    ("mclaren_720s", 1.2, "C"), ("bed_2K", 0.7, "L"),
    ("tank_2K", 2.6, "C"), ("jnr-c62", 4.0, "R"),
    ("european-maple", 6.0, "L"), ("cat_figurine", 0.6, "R"),
]


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs
           if o.type == "MESH" and not o.hide_render for c in o.bound_box]
    if not pts:
        return None
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def transform(objs, mat: Matrix):
    group = set(objs)
    for o in objs:
        if o.parent in group:
            continue
        o.matrix_world = mat @ o.matrix_world
    bpy.context.view_layer.update()


def load_lot(pattern):
    blend = dm.find_blend(pattern)
    if blend is None:
        import scan_models
        blend = next((m["path"] for m in scan_models.scan(scan_models.DEFAULT_ROOT)
                      if pattern in Path(m["path"]).stem), None)
    if blend is None:
        say(f"見つからない: {pattern}")
        return []
    before = set(bpy.data.objects)
    meshes, others = fp_batch.append_objects(blend)
    fresh = set(bpy.data.objects) - before
    meshes = [o for o in meshes if o in fresh]
    others = [o for o in others if o in fresh]
    if not meshes:
        return []
    shape = set()
    for a in others:
        if a.type == "ARMATURE" and a.pose:
            for pb in a.pose.bones:
                if pb.custom_shape is not None:
                    shape.add(pb.custom_shape.name)
    for o in meshes:
        if o.name in shape or o.name.lower().startswith(("cs_", "wgt", "shape_")):
            o.hide_render = True
    content = [o for o in meshes if not o.hide_render] or meshes
    cluster = fp_batch.dominant_cluster(content)
    for o in content:
        if o not in cluster:
            o.hide_render = True
    fp_batch.normalize(meshes + others, [o for o in content if o in cluster] or content)
    bpy.context.view_layer.update()
    return meshes + others


def build_town():
    bpy.ops.wm.read_homefile(use_empty=True)
    rng = random.Random(7)
    all_meshes = []
    y = 0.0
    road_half = 4.0          # 通りの半幅
    for i, (pat, height, side) in enumerate(LOTS):
        objs = load_lot(pat)
        if not objs:
            continue
        bb = bounds(objs)
        if bb is None:
            continue
        size = bb[1] - bb[0]
        s = height / max(size.z, 1e-6)
        transform(objs, Matrix.Scale(s, 4))
        bb = bounds(objs)
        size = bb[1] - bb[0]
        # 足元を地面に、中心を x=0 に
        transform(objs, Matrix.Translation(Vector((-(bb[0].x + bb[1].x) / 2,
                                                   -(bb[0].y + bb[1].y) / 2,
                                                   -bb[0].z))))
        # 向き: 通りの方を向くように、左右で回す
        if side == "L":
            x = -(road_half + size.x / 2 + rng.uniform(0.5, 2.0))
            rot = math.radians(90 + rng.uniform(-8, 8))
        elif side == "R":
            x = road_half + size.x / 2 + rng.uniform(0.5, 2.0)
            rot = math.radians(-90 + rng.uniform(-8, 8))
        else:
            # 通りの真ん中だとカメラが貫通する。道の端に交互に寄せる
            x = (2.6 if i % 2 == 0 else -2.6) + rng.uniform(-0.3, 0.3)
            rot = math.radians(rng.uniform(-6, 6))
        # 通りに沿った長さ。大物(ハンガー)で 40 単位の空白ができたので上限
        along = min(max(size.y, size.x), 8.0)
        y += along * 0.5 + rng.uniform(0.3, 1.2)
        transform(objs, Matrix.Translation(Vector((x, y, 0))) @ Matrix.Rotation(rot, 4, "Z"))
        y += along * 0.5
        all_meshes += [o for o in objs if o.type == "MESH" and not o.hide_render]
        say(f"{i:2d} {pat:<22} 高さ{height:4.1f} 側{side} y={y:6.1f}")
    return all_meshes, y


def stage(meshes, length):
    sc = bpy.context.scene
    dm.grey(meshes)
    # 地面: 線が出ないよう1枚の平面。白プレビューの代わりにモノ光を
    # 使うので、地面にも薄い陰影(モデルの影)が落ちる
    bpy.ops.mesh.primitive_plane_add(size=1)
    ground = bpy.context.object
    # 地平線に縁の線が出ないよう、視界より遥かに大きく
    ground.scale = (4000, 4000, 1)
    ground.location = (0, length / 2, -0.01)
    dm.grey([ground])
    # 地面は STEP1 の塗り分けに入れない。入れると地平線(地面と空の境)が
    # 輪郭として太い線になり、黒い帯が出た(実測)。塗らなければ AOV が
    # 背景と同じ黒になり、境が出ない。モデルの影は陰影のパスから出る
    ground.name = "FP_ground"
    cd = bpy.data.cameras.new("C")
    cd.lens = 32.0
    cd.clip_end = 6000
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        # 空を白く強くすると直接光パスに空の光が入って影が埋まった(実測)。
        # 空は暗いままにし、透明背景で撮って組み立て時に白へ載せる
        bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1)
        bg.inputs[1].default_value = 0.15
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = math.radians(2.0)
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(50), 0, math.radians(-35))
    return cam


def aim(cam, f, length):
    """通りの上を進み、少し左右を見る"""
    t = f / max(FRAMES - 1, 1)
    yy = -6.0 + (length - 28.0) * t
    x = 0.4 * math.sin(t * math.pi * 2.0)
    cam.location = (x, yy, 1.6)
    yaw = math.radians(12.0) * math.sin(t * math.pi * 3.0)
    cam.rotation_euler = (math.radians(90.0), 0.0, yaw)
    bpy.context.view_layer.update()


def main():
    fp_batch.install_addon()
    meshes, length = build_town()
    say(f"モデル {len(meshes)} 個、通りの長さ {length:.1f}")
    cam = stage(meshes, length)
    sc = bpy.context.scene
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.fp_auto_style = STYLE
    sc.fp_gap_fill = GAP
    sc.fp_lw_ink = INK
    sc.fp_lw_soften = SOFTEN
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    # しきい値の計測は通りの真ん中あたりで
    aim(cam, FRAMES // 2, length)
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert sc.render.resolution_percentage == 200
    say(f"しきい値 {[round(getattr(sc, f'fp_lw_e{i}'), 4) for i in range(1, 5)]}  "
        f"密度 {getattr(sc, 'fp_lw_density', -1):.3f}")
    # 地平線(地面の奥と空)の深度差が太い帯になる(実測)。深度は切る
    sc.fp_ch_depth = 0.0
    # 手描き背景: 奥の距離は深度チャンネルを切ってから測り直す。STEP0 の
    # 計測は地平線の帯(深度チャンネル)まで線に数えて、奥の終わりが 238 に
    # なった(実測。切ると 71)
    if sc.fp_lw_far > 0.0 or sc.fp_lw_far_sens > 1.0:
        bpy.ops.freepencil.measure_line_weight()
        bpy.ops.freepencil2.link_button()
        say(f"奥の扱い 細く{sc.fp_lw_far:g} 減らす{sc.fp_lw_far_sens:g} "
            f"薄く{sc.fp_lw_far_fade:g}  距離 {sc.fp_lw_far_start:.1f}..{sc.fp_lw_far_end:.1f}  "
            f"葉の房 {sc.fp_foliage_clumps}  隙間 {sc.fp_gap_fill}")
    # 薄い陰影: モノ光プレビュー。床を高くして薄く
    sc.fp_mono_floor = MONO_FLOOR
    sc.fp_preview_mode = 'MONO_LIGHT'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "town.blend"))
    for f in range(START, FRAMES):
        aim(cam, f, length)
        sc.frame_set(f + 1)
        fp_batch.render_still(sc, OUT / "seq" / f"f{f:04d}.png", 1)
        if (f + 1) % 24 == 0:
            say(f"  {f + 1}/{FRAMES}")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
