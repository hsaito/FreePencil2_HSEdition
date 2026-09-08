"""BlenderKit のアセットで町を組み、通りを進む線画ムービーを作る。

建物・木・車をリンク複製で並べる。同じメッシュ実体を共有するので、
STEP1 は代表1体だけを塗れば済む(v2.6.0 の重複排除がそのまま効く)。

  blender -b --factory-startup --python make_town_movie.py -- \
      --out <dir> [--frames 120] [--res 960] [--fps 24] [--relief 0.6]
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "town"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
FRAMES = int(arg("--frames", "120"))
RES = int(arg("--res", "960"))
SS = int(arg("--ss", "2"))
FPS = int(arg("--fps", "24"))
RELIEF = float(arg("--relief", "0.6"))
SEED = int(arg("--seed", "7"))
MONO_LIGHT = "--no-mono" not in ARGV
FLOOR = float(arg("--floor", "0.35"))
LOGO_TEXT = arg("--logo", "FreePencil2")
LOGO_H = float(arg("--logo-height", "6.0"))
T0 = time.time()
rnd = random.Random(SEED)


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# 通りに並べるもの。high は「奥に置く」= 遠景のつぶれを作る対象
PARTS = {
    "apartment": "050_japan-apartment",
    "house": "066_modern-house",
    "tree": "096_tree_autumn",
    "car_a": "022_cartoon-car-cabriolet",
    "car_b": "023_cartoon-wagon-car",
    "car_c": "059_low-poly-car",
    "bench": "062_manchester-acacia-outdoor-bench",
}


def load_part(models: dict, key: str, target_h: float):
    """アセットを1つ読み込み、原点合わせ+高さ正規化した「型」を返す。

    戻り値は (代表オブジェクトのリスト, 実サイズ)。以後はこれを
    リンク複製して並べる。
    """
    name = PARTS[key]
    entry = next((m for m in models.values() if m["name"].startswith(name)),
                 None)
    if entry is None:
        say(f"見つからない: {name}")
        return None, 0.0
    meshes, others = fp_batch.append_objects(Path(entry["path"]))
    if not meshes:
        return None, 0.0
    objs = meshes + others

    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    size = mx - mn
    scale = target_h / max(size.z, 1e-6)

    # 親を作って一括で動かせるようにする
    root = bpy.data.objects.new(f"PART_{key}", None)
    bpy.context.scene.collection.objects.link(root)
    for o in objs:
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = root.matrix_world.inverted()
    root.scale = (scale, scale, scale)
    # 底面を原点へ、水平方向は中央へ
    root.location = (-(mn.x + mx.x) * 0.5 * scale,
                     -(mn.y + mx.y) * 0.5 * scale,
                     -mn.z * scale)
    bpy.context.view_layer.update()
    faces = sum(len(o.data.polygons) for o in meshes)
    say(f"読み込み {key:<10} {entry['name'][:34]:<36} {faces:>8,}面 "
        f"元の高さ {size.z:.1f}m -> {target_h:.1f}m")
    root.hide_render = True
    for o in objs:
        o.hide_render = True
    return root, faces


def _dup_tree(obj, parent):
    """階層ごと複製する。obj.copy() はメッシュ実体を共有する(=リンク複製)。

    子だけを浅く複製すると、その孫が落ちて中身がほとんど消える
    (最初こう書いて、64個置いたはずが1メッシュしか出なかった)。
    """
    c = obj.copy()
    c.parent = parent
    if parent is not None:
        c.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
    c.hide_render = False
    bpy.context.scene.collection.objects.link(c)
    for ch in obj.children:
        _dup_tree(ch, c)
    return c


def place(root, loc, rot_z=0.0, scale=1.0):
    """型をリンク複製して置く(メッシュ実体は共有される)。"""
    new_root = _dup_tree(root, None)
    new_root.location = loc
    new_root.rotation_euler = (0.0, 0.0, rot_z)
    new_root.scale = tuple(v * scale for v in root.scale)
    return new_root


def build_town(models) -> dict:
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene

    parts = {}
    total_src = 0
    for key, h in (("apartment", 12.0), ("house", 6.0), ("tree", 7.0),
                   ("car_a", 1.5), ("car_b", 1.6), ("car_c", 1.4),
                   ("bench", 0.9)):
        root, faces = load_part(models, key, h)
        if root is not None:
            parts[key] = root
            total_src += faces

    # --- 通り: Y方向に伸ばし、両側に建物を並べる
    ROAD_W = 9.0
    SPACING = 11.0
    ROWS = 14
    placed = 0
    for i in range(ROWS):
        y = -i * SPACING
        for side in (-1, 1):
            x = side * (ROAD_W * 0.5 + 6.0)
            key = "apartment" if (i + (side > 0)) % 2 == 0 else "house"
            if key not in parts:
                continue
            place(parts[key], (x, y, 0.0),
                  rot_z=math.pi / 2 * (1 if side < 0 else -1),
                  scale=rnd.uniform(0.85, 1.15))
            placed += 1
        # 歩道の木
        if "tree" in parts:
            for side in (-1, 1):
                place(parts["tree"],
                      (side * (ROAD_W * 0.5 + 1.2), y - SPACING * 0.5, 0.0),
                      rot_z=rnd.uniform(0, 6.28),
                      scale=rnd.uniform(0.8, 1.2))
                placed += 1
        # 路肩の車(数台おき)
        if i % 3 == 1:
            key = rnd.choice([k for k in ("car_a", "car_b", "car_c")
                              if k in parts] or [None])
            if key:
                side = rnd.choice((-1, 1))
                place(parts[key], (side * (ROAD_W * 0.5 - 1.4), y, 0.0),
                      rot_z=math.pi if side > 0 else 0.0)
                placed += 1
        if i % 4 == 2 and "bench" in parts:
            place(parts["bench"], (-(ROAD_W * 0.5 + 1.0), y + 3.0, 0.0),
                  rot_z=math.pi / 2)
            placed += 1

    # --- 路面
    bpy.ops.mesh.primitive_plane_add(size=1)
    road = bpy.context.object
    road.name = "ROAD"
    road.scale = (ROAD_W * 0.5, ROWS * SPACING, 1.0)
    road.location = (0.0, -ROWS * SPACING * 0.5 + SPACING, 0.01)

    light = bpy.data.lights.new("Sun", type="SUN")
    light.energy = 3.5
    sun = bpy.data.objects.new("Sun", light)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(52), 0, math.radians(35))

    meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    uniq = {o.data.name for o in meshes}
    say(f"町ができた: 配置 {placed} / メッシュ {len(meshes)} / "
        f"メッシュ実体 {len(uniq)} / 面(実体) "
        f"{sum(len(m.polygons) for m in bpy.data.meshes):,}")
    return {"placed": placed, "objects": len(meshes), "unique": len(uniq),
            "rows": ROWS, "spacing": SPACING}


def add_logo(info, text="FreePencil2", height=6.0):
    """通りの突き当たりに立体文字を置く。ラストのカメラはここへ寄る。

    テキストオブジェクトのままでは頂点カラーを塗れないのでメッシュ化する。
    押し出しとベベルを付けて、面の向きの差から線が出るようにしておく。
    """
    scene = bpy.context.scene
    span = info["rows"] * info["spacing"]
    y = -span - 6.0                       # 通りの奥、建物列の先

    cur = bpy.data.curves.new("LogoText", type="FONT")
    cur.body = text
    cur.align_x = "CENTER"
    cur.align_y = "BOTTOM"
    cur.extrude = 0.22                    # 厚み
    cur.bevel_depth = 0.035               # 角に丸み = 稜線が線になる
    cur.bevel_resolution = 2
    obj = bpy.data.objects.new("FP_LOGO", cur)
    scene.collection.objects.link(obj)
    obj.location = (0.0, y, 1.2)
    obj.rotation_euler = (math.radians(90), 0.0, 0.0)  # 正面をカメラへ

    # メッシュ化(頂点カラーを塗る対象にする)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object

    # 文字高さを合わせる
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    cur_h = max(mx.z - mn.z, 1e-6)
    k = height / cur_h
    obj.scale = (k, k, k)
    bpy.context.view_layer.update()
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    obj.location = (obj.location.x, y, obj.location.z - mn.z + 1.2)

    # 背後の壁(文字を浮き立たせる)
    bpy.ops.mesh.primitive_plane_add(size=1)
    wall = bpy.context.object
    wall.name = "LOGO_WALL"
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    wall.scale = (26.0, 12.0, 1.0)
    wall.location = (0.0, y + 1.6, 8.0)

    say(f"ロゴ '{text}' を y={y:.1f} に配置 "
        f"({len(obj.data.polygons):,}面)")
    return obj, y


def add_camera(info) -> bpy.types.Object:
    """通りの入口から奥へ進むカメラ。少しだけ左右に振って画に動きを出す。"""
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("TownCam")
    cam_data.lens = 30.0
    cam_data.clip_end = 400.0
    cam = bpy.data.objects.new("TownCam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    span = info["rows"] * info["spacing"]
    logo_y = info.get("logo_y", -span - 6.0)
    # 通りを抜けて、最後の LAST の区間でロゴの正面へ寄る
    LAST = 0.22
    y0 = 8.0
    y1 = logo_y + 26.0        # ロゴ手前で止まる
    for f in range(FRAMES):
        t = f / max(FRAMES - 1, 1)
        y = y0 + (y1 - y0) * t
        if t < 1.0 - LAST:
            # 通りを進む。左右に振って画に動きを出す
            sway = math.sin(t * math.pi * 2.0) * 1.6
            cam.location = (sway, y, 1.7 + math.sin(t * math.pi) * 0.25)
            look = Vector((math.sin(t * math.pi * 2.0 + 0.6) * 2.2,
                           y - 18.0, 2.0))
        else:
            # ロゴへ寄る。揺れを収めて正面・目線を上げる
            u = (t - (1.0 - LAST)) / LAST          # 0 -> 1
            e = u * u * (3.0 - 2.0 * u)            # なめらかに
            sway = math.sin(t * math.pi * 2.0) * 1.6 * (1.0 - e)
            cam.location = (sway, y,
                            1.7 + math.sin(t * math.pi) * 0.25 + e * 2.6)
            look = Vector((sway * (1.0 - e), logo_y, 1.2 + e * 3.4))
        d = look - cam.location
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f + 1)
        cam.keyframe_insert("rotation_euler", frame=f + 1)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    scene.frame_start = 1
    scene.frame_end = FRAMES
    return cam


def add_mono_light(scene, floor=0.35) -> None:
    """線画に陰影を掛けてモノクロ仕上げにする。

    STEP3 の出力は Group.sample = 白地に黒線。そこへレンダ画像を
    グレースケール化したものを乗算すると、線はそのまま、面に陰影が乗る。
    floor は影の下限で、0 にすると暗部が潰れて線が見えなくなる。

    2倍レンダ→50%縮小の Scale より手前に挿す(両方とも200%の絵なので
    そこで掛ければ、縮小は最後に1回で済む)。
    """
    tree = fp_batch.comp_tree(scene)
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    scale = next((n for n in tree.nodes if n.type == "SCALE"), None)
    comp = next(n for n in tree.nodes if n.type in ("COMPOSITE", "GROUP_OUTPUT"))
    sink = scale if scale is not None else comp
    if not sink.inputs[0].is_linked:
        say("モノクロ合成: 差し込み先が見つからない")
        return
    line_src = sink.inputs[0].links[0].from_socket

    bw = tree.nodes.new("CompositorNodeRGBToBW")
    bw.label = "fp_mono"
    bw.location = (rl.location.x + 260, rl.location.y - 420)
    tree.links.new(rl.outputs["Image"], bw.inputs[0])

    # 暗部を floor まで持ち上げる(潰さない)
    lift = tree.nodes.new("CompositorNodeMapRange")
    lift.label = "fp_mono"
    lift.location = (bw.location.x + 180, bw.location.y)
    for name, val in (("From Min", 0.0), ("From Max", 1.0),
                      ("To Min", floor), ("To Max", 1.0)):
        sock = lift.inputs.get(name)
        if sock is not None:
            sock.default_value = val
    lift.use_clamp = True
    tree.links.new(bw.outputs[0], lift.inputs[0])

    mul = tree.nodes.new("CompositorNodeMixRGB")
    mul.label = "fp_mono"
    mul.blend_type = "MULTIPLY"
    mul.location = (sink.location.x - 180, sink.location.y - 200)
    mul.inputs[0].default_value = 1.0
    tree.links.new(line_src, mul.inputs[1])
    tree.links.new(lift.outputs[0], mul.inputs[2])
    tree.links.new(mul.outputs[0], sink.inputs[0])
    say(f"モノクロ合成を挿入 (影の下限 {floor})")


def main() -> None:
    fp_batch.install_addon()
    models = {m["name"]: m for m in scan_models.scan(scan_models.DEFAULT_ROOT)}
    info = build_town(models)
    _logo, logo_y = add_logo(info, LOGO_TEXT, LOGO_H)
    info["logo_y"] = logo_y
    add_camera(info)

    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False

    meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    say(f"STEP0 完了 {time.time() - t:.1f}s")

    if MONO_LIGHT:
        add_mono_light(scene, FLOOR)

    if RELIEF > 0:
        from freepencil2 import fp_core
        scene.fp_far_relief = RELIEF
        for ng in bpy.data.node_groups:
            if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
                fp_core.far_relief_from_scene(ng, scene)
        say(f"遠景つぶれ軽減 {RELIEF}")

    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    # アドオンの細線化(200%+Scale 0.5)に render_still の箱縮小を重ねると
    # 絵ごと半分に縮んで線が灰色に潰れる。素直に2倍で描いて縮小する
    # (実測: ink 0.00174 → 0.00836, 真っ黒画素 0.00001 → 0.00368)
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = RES * SS
    scene.render.resolution_y = int(RES * 9 / 16) * SS
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    frame_dir = OUT / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    t = time.time()
    for f in range(1, FRAMES + 1):
        scene.frame_set(f)
        png = frame_dir / f"f{f:04d}.png"
        fp_batch.render_still(scene, png, SS)
        paths.append(png)
        if f % 20 == 0 or f == FRAMES:
            say(f"  {f}/{FRAMES} フレーム ({time.time() - t:.0f}s)")
    say(f"レンダ完了 {time.time() - t:.1f}s")

    video = OUT / "town_lineart.mp4"
    fp_batch.encode_video(paths, video, FPS, RES, int(RES * 9 / 16))
    say(f"動画 {video} ({video.stat().st_size // 1024} KB)")

    blend = OUT / "town.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    say(f"保存 {blend}")
    (OUT / "info.json").write_text(json.dumps(info, indent=1,
                                              ensure_ascii=False),
                                   encoding="utf-8")


if __name__ == "__main__":
    main()
