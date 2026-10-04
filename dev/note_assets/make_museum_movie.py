"""線の映えるモデルを博物館に並べて、奥へ進むカメラで撮る。

白飛ばし(エミッション)ではなく、灰色のディフューズ+照明にする。
陰影が出たうえに線が乗るので、模型を並べた展示室に見える。

    blender -b --factory-startup --python make_museum_movie.py -- \
        [--frames 120] [--res 1280] [--test 1]

--test 1 なら 1 枚だけ撮って終わる(構図確認用)。
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "museum"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
FRAMES = int(arg("--frames", "120"))
RES_W = int(arg("--res", "1280"))
RES_H = int(RES_W * 9 / 16)
FPS = int(arg("--fps", "24"))
SS = int(arg("--ss", "2"))
TEST = int(arg("--test", "0"))
ROOT = Path(arg("--root", str(Path.home() / "blenderkit_data" / "models")))
T0 = time.time()

# 展示物。線の量で選んだ(out/gallery の実測)。左右交互に置く
EXHIBITS = [
    ("088_tank", "tank_2K_0fab3afc*", 1.55),
    ("020_camera", "camera_2K_d98f03a9*", 1.30),
    ("051_c58", "jnr-c58-steam-locomotive_2K_d4845aae*", 1.70),
    ("083_squid", "squid_with_procedural_texturing_52e20060*", 1.45),
    ("076_kuka", "robot-kuka-quantec-with-palet-gripper_2K*", 1.70),
    ("032_ship", "dutch_ship_medium_2K_b67c0a0d*", 1.60),
    ("053_mech", "kaino-school-military-mech_2K_2fdfaccf*", 1.75),
    ("034_eiffel", "eiffel_tower_1892_4da8ea24*", 1.90),
]
END_PIECE = ("086_frank", "stylized-male-character-model-frank_2K_3*", 1.80)

SPACING = 5.0        # 展示台の間隔(奥行き)
SIDE = 3.0           # 中心線からの左右の距離
HALL_W = 9.0
HALL_H = 6.0
PED_H = 1.0
PED_R = 1.15         # 台の半径(角柱の半幅)


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def find_blend(pattern):
    hits = sorted(ROOT.glob(f"*/{pattern}.blend"))
    return hits[0] if hits else None


# ------------------------------------------------------------------ 建物
def box(name, size, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return o


def build_hall(depth):
    """床・壁・天井・柱・展示台。線を出すために面を分けて作る。"""
    parts = []
    z0, z1 = -depth * 0.15, depth
    mid = (z0 + z1) * 0.5
    length = z1 - z0
    parts.append(box("Floor", (HALL_W, length, 0.3), (0, mid, -0.15)))
    parts.append(box("Ceil", (HALL_W, length, 0.3), (0, mid, HALL_H + 0.15)))
    for s in (-1, 1):
        parts.append(box(f"Wall{s}", (0.3, length, HALL_H),
                         (s * HALL_W * 0.5, mid, HALL_H * 0.5)))
    # 柱と天井の梁。奥行きのリズムを作る
    n = int(length // SPACING) + 1
    for i in range(n):
        y = z0 + i * SPACING
        for s in (-1, 1):
            parts.append(box(f"Col{i}{s}", (0.55, 0.55, HALL_H),
                             (s * (HALL_W * 0.5 - 0.4), y, HALL_H * 0.5)))
            parts.append(box(f"Cap{i}{s}", (0.8, 0.8, 0.25),
                             (s * (HALL_W * 0.5 - 0.4), y, HALL_H - 0.5)))
        parts.append(box(f"Beam{i}", (HALL_W, 0.5, 0.45),
                         (0, y, HALL_H - 0.25)))
    # 奥の壁
    parts.append(box("Back", (HALL_W, 0.3, HALL_H), (0, z1, HALL_H * 0.5)))
    return parts


def pedestal(name, loc):
    a = box(name + "_base", (PED_R * 2 + 0.2, PED_R * 2 + 0.2, 0.12),
            (loc[0], loc[1], 0.06))
    b = box(name + "_body", (PED_R * 1.75, PED_R * 1.75, PED_H - 0.2),
            (loc[0], loc[1], (PED_H - 0.2) * 0.5 + 0.12))
    c = box(name + "_top", (PED_R * 2, PED_R * 2, 0.08),
            (loc[0], loc[1], PED_H - 0.04))
    return [a, b, c]


# ------------------------------------------------------------------ 展示物
def place(blend, target_h, at, rot_z):
    """アセットを読み込み、台の上に高さを揃えて置く。"""
    meshes, others = fp_batch.append_objects(blend)
    if not meshes:
        return []
    # リグの操作シェイプと外れジオメトリは隠す(枠取りが壊れるため)
    shape_names = set()
    for a in others:
        if a.type == "ARMATURE" and a.pose:
            for pb in a.pose.bones:
                if pb.custom_shape is not None:
                    shape_names.add(pb.custom_shape.name)
    for o in meshes:
        if (o.name in shape_names
                or o.name.lower().startswith(("cs_", "wgt", "shape_"))):
            o.hide_render = True
    content = [o for o in meshes if not o.hide_render] or meshes
    cluster = fp_batch.dominant_cluster(content)
    for o in content:
        if o not in cluster:
            o.hide_render = True
    framed = [o for o in content if o in cluster] or content

    bpy.context.view_layer.update()
    mn = Vector((1e18,) * 3)
    mx = Vector((-1e18,) * 3)
    for o in framed:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    h = max(mx.z - mn.z, 1e-6)
    s = target_h / h
    pivot = Vector(((mn.x + mx.x) * 0.5, (mn.y + mx.y) * 0.5, mn.z))
    M = (Matrix.Translation(Vector(at))
         @ Matrix.Rotation(rot_z, 4, 'Z')
         @ Matrix.Scale(s, 4)
         @ Matrix.Translation(-pivot))
    for o in meshes + others:
        if o.parent is None:
            o.matrix_world = M @ o.matrix_world
    return meshes + others


# ------------------------------------------------------------------ 画作り
def grey_material(meshes):
    """全部を同じ灰色のディフューズにする。色は無し、陰影だけ残す。"""
    mat = bpy.data.materials.new("FP_Museum")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
    bsdf.inputs["Color"].default_value = (0.80, 0.80, 0.79, 1.0)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (240, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    for o in meshes:
        o.data.materials.clear()
        o.data.materials.append(mat)


def light_hall(depth):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("FP_W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
        bg.inputs[1].default_value = 0.5
    sc.world = w
    n = int(depth // SPACING) + 2
    for i in range(n):
        y = -depth * 0.15 + i * SPACING - SPACING * 0.5
        lt = bpy.data.lights.new(f"L{i}", type="AREA")
        lt.shape = 'RECTANGLE'
        lt.size, lt.size_y = 6.0, 2.4
        lt.energy = 120.0
        lo = bpy.data.objects.new(f"L{i}", lt)
        sc.collection.objects.link(lo)
        lo.location = (0.0, y, HALL_H - 0.9)
        lo.rotation_euler = (0.0, 0.0, 0.0)
    # 入口からの弱い順光。奥が黒く沈まないように
    lt = bpy.data.lights.new("Fill", type="AREA")
    lt.size = 10.0
    lt.energy = 70.0
    lo = bpy.data.objects.new("Fill", lt)
    sc.collection.objects.link(lo)
    lo.location = (0.0, -depth * 0.2, 2.6)
    lo.rotation_euler = (math.radians(90), 0.0, 0.0)


def make_camera(depth, stop_y):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 30.0
    cd.clip_start = 0.05
    cd.clip_end = depth * 4
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    y0 = -depth * 0.12
    # 突き当たりの展示物を正面に収める位置で停める
    y1 = stop_y - SPACING * 2.0
    sc.frame_start = 1
    sc.frame_end = FRAMES
    for f, t in ((1, 0.0), (FRAMES, 1.0)):
        # 等速だと機械的なので、入りと終わりを少し緩める
        e = t * t * (3.0 - 2.0 * t)
        cam.location = (0.0, y0 + (y1 - y0) * e, 1.62 + 0.10 * e)
        cam.keyframe_insert("location", frame=f)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    return cam


# ------------------------------------------------------------------ 本体
def main():
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene

    n_slot = len(EXHIBITS)
    depth = SPACING * (n_slot / 2 + 1.6)
    build_hall(depth)

    placed = []
    end_y = depth - SPACING
    for i, (name, pat, h) in enumerate(EXHIBITS):
        blend = find_blend(pat)
        if blend is None:
            say(f"{name}: 見つからない ({pat})")
            continue
        side = -1 if i % 2 == 0 else 1
        y = i // 2 * SPACING + SPACING * 0.5
        pedestal(f"P{i}", (side * SIDE, y, 0.0))
        # カメラは -Y から来る。真正面(0度)から少し振って四分の三に
        rot = math.radians(38.0 if side < 0 else -38.0)
        objs = place(blend, h, (side * SIDE, y, PED_H), rot)
        placed.append((name, len(objs)))
        say(f"置いた {name} ({'左' if side < 0 else '右'} y={y:.1f})")

    blend = find_blend(END_PIECE[1])
    if blend is not None:
        y = (n_slot // 2) * SPACING + SPACING * 0.4
        end_y = y
        pedestal("PEnd", (0.0, y, 0.0))
        place(blend, END_PIECE[2], (0.0, y, PED_H), 0.0)
        say(f"置いた {END_PIECE[0]} (正面 y={y:.1f})")

    meshes = [o for o in sc.objects if o.type == "MESH"]
    grey_material(meshes)
    light_hall(depth)
    cam = make_camera(depth, end_y)
    say(f"面 合計 {sum(len(o.data.polygons) for o in meshes):,}")

    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    # 白飛ばしではなく陰影のみ。ディフューズ直接光をグレースケール化
    # して PRO ノードの下地にする(fp_core.set_mono_light_preview)
    sc.fp_preview_mode = 'MONO_LIGHT'
    sc.fp_mono_floor = 0.30
    # 2倍レンダは render_still 側で行う。両方でやると絵が半分の大きさで
    # 焼かれる(過去に踏んだ)
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    fp_batch.select_meshes()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    # STEP0 がプレビュー種別を戻すことがあるので後から立て直す
    sc.fp_auto_white_preview = False
    sc.fp_preview_mode = 'MONO_LIGHT'
    sc.fp_mono_floor = 0.30
    say(f"STEP0 完了 / プレビュー={sc.fp_preview_mode}")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    # render_still(ss) は「シーンの解像度でレンダしてから 1/ss に縮小」する。
    # 解像度を ss 倍にするのは呼び出し側の仕事。ここを 1 倍にしていると
    # 出来上がりが 1/ss になり、動画では引き伸ばされて眠くなる(実測で踏んだ)
    sc.render.resolution_x = RES_W * SS
    sc.render.resolution_y = RES_H * SS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "museum.blend"))

    frames_dir = OUT / "frames"
    frames_dir.mkdir(exist_ok=True)
    if TEST:
        for f in (1, FRAMES // 2, FRAMES):
            sc.frame_set(f)
            fp_batch.render_still(sc, OUT / f"test_{f:04d}.png", SS)
            say(f"試写 {f}")
        return

    paths = []
    for f in range(1, FRAMES + 1):
        sc.frame_set(f)
        p = frames_dir / f"f{f:04d}.png"
        fp_batch.render_still(sc, p, SS)
        paths.append(p)
        if f % 10 == 0 or f == 1:
            say(f"{f}/{FRAMES}")
    mp4 = OUT / "museum.mp4"
    fp_batch.encode_video(paths, mp4, FPS, RES_W, RES_H)
    say(f"完了 {mp4}")


if __name__ == "__main__":
    main()
