"""60秒デモのメカのカット: KUKA のパレットグリッパーが、左のパレットの山から
一番上の1枚をつかんで右の山へ移す(12 秒)。仕上がりは精密。

KUKA のロゴや銘板はテクスチャなので、線画(白い材質/モノクロの陰影)には
写らない。材質の色のままの絵は撮らないこと。モデル名の文字オブジェクトは消す。

  blender -b --factory-startup --python make_kuka_demo.py -- --build
      シーンを作って STEP0(精密)まで掛けて保存(out/demo60/kuka.blend)
  blender -b --factory-startup --python make_kuka_demo.py -- --stills 1,70,150,230 [--res 960]
  blender -b --factory-startup --python make_kuka_demo.py -- --movie [--preview]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "demo60"))).resolve()
SRC = next((Path.home() / "blenderkit_data" / "models").glob(
    "robot-kuka-quant*/robot-kuka-quantec*.blend"))
FPS = 24
FRAMES = int(arg("--frames", "288"))          # 12 秒
PALLET_H = 0.144

sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import numpy as np                # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402
from town_kit import MB           # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)

YAW_PICK = math.radians(62.0)     # 左の山(カメラから見て右手前へ振る)
YAW_PLACE = math.radians(-62.0)
RADIUS = 2.05                     # 台座の軸から山の中心まで
N_PICK, N_PLACE = 6, 3            # 山の枚数(つかむのは左の一番上)


# ---------------------------------------------------------------- 周り

def pallet(name):
    """1.2 x 0.8 x 0.144 のパレット。上面の中心が原点。長い辺が x。"""
    mb = MB(name)
    for i in range(7):                                   # 上の板
        mb.box(-0.6 + 0.1 + i * (1.0 / 6.0), 0, -0.011, 0.14, 0.8, 0.022)
    for y in (-0.36, 0.0, 0.36):                         # 桁
        mb.box(0, y, -0.033, 1.2, 0.1, 0.022)
    for x in (-0.53, 0.0, 0.53):                         # ブロック
        for y in (-0.36, 0.0, 0.36):
            mb.box(x, y, -0.083, 0.14, 0.1, 0.078)
    for x in (-0.53, 0.0, 0.53):                         # 下の板
        mb.box(x, 0, -0.133, 0.14, 0.8, 0.022)
    return mb.build()


def stack_matrix(yaw, level):
    """山の level 枚目(0 始まり)の上面中心。グリッパーと向きを合わせる。"""
    x = math.sin(yaw) * RADIUS
    y = -math.cos(yaw) * RADIUS
    return (Matrix.Translation((x, y, PALLET_H * (level + 1)))
            @ Matrix.Rotation(yaw, 4, "Z"))


def floor_and_fence():
    mb = MB("floor")
    mb.box(0, 0, -0.01, 40, 40, 0.02)
    # 安全区画の白線(4.6m 四方、幅 0.08)と、台座まわりの目地
    for s in (-1, 1):
        mb.box(s * 2.3, -0.4, 0.002, 0.08, 4.6, 0.004)
        mb.box(0, -0.4 + s * 2.3, 0.002, 4.6, 0.08, 0.004)
    floor = mb.build()
    # 奥(+y)に安全柵: 柱 1.2m おき、枠と縦の格子
    fb = MB("fence")
    y = 1.9
    for i in range(-4, 5):
        x = i * 1.2
        fb.box(x, y, 1.0, 0.06, 0.06, 2.0)
        if i < 4:
            fb.box(x + 0.6, y, 0.25, 1.14, 0.03, 0.03)
            fb.box(x + 0.6, y, 1.95, 1.14, 0.03, 0.03)
            for k in range(1, 6):
                fb.box(x + k * (1.2 / 6), y, 1.1, 0.012, 0.012, 1.7)
    fence = fb.build()
    return [floor, fence]


# ---------------------------------------------------------------- 腕の関節

J = {}                                   # 名前 -> オブジェクト


def joints():
    for n in ("Link.1", "Link2", "Link.3", "Link.5", "Clamp.lever", "Main frame"):
        J[n] = bpy.data.objects[n]
    J["rest5"] = J["Link.5"].rotation_euler.x


def set_pose(yaw, a2, a3, wrist_sign):
    J["Link.1"].rotation_euler.z = yaw
    J["Link2"].rotation_euler.x = a2
    J["Link.3"].rotation_euler.x = a3
    J["Link.5"].rotation_euler.x = J["rest5"] + wrist_sign * (a2 + a3)


def grip_world():
    """グリッパーでつかむ点(左右のクランプの下の面の中心)の世界行列。"""
    bpy.context.view_layer.update()
    mf = J["Main frame"].matrix_world
    return mf @ Matrix.Translation(J["grip_local"])


def measure_grip():
    bpy.context.view_layer.update()
    pts = []
    for n in ("Pallet clamp.001", "Pallet clamp.002"):
        o = bpy.data.objects[n]
        pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    zmin = min(p.z for p in pts)
    mf = J["Main frame"].matrix_world
    c = mf.translation
    J["grip_local"] = mf.inverted_safe().to_3x3() @ (Vector((c.x, c.y, zmin)) - c)


def solve(yaw, target, wrist_sign):
    """つかむ点を target に置く肩・肘の角度を、粗い格子 -> 細かい格子で探す。"""
    best = None
    for lo2, hi2, lo3, hi3, st in ((-25, 100, -150, 60, 4.0),):
        for a2 in np.arange(lo2, hi2, st):
            for a3 in np.arange(lo3, hi3, st):
                set_pose(yaw, math.radians(a2), math.radians(a3), wrist_sign)
                e = (grip_world().translation - target).length
                if best is None or e < best[0]:
                    best = (e, a2, a3)
    for st in (1.0, 0.25, 0.06):
        _, b2, b3 = best
        for a2 in np.arange(b2 - 4 * st, b2 + 4 * st + 1e-9, st):
            for a3 in np.arange(b3 - 4 * st, b3 + 4 * st + 1e-9, st):
                set_pose(yaw, math.radians(a2), math.radians(a3), wrist_sign)
                e = (grip_world().translation - target).length
                if e < best[0]:
                    best = (e, a2, a3)
    return best


LOGO = {}                                 # 物の名前 -> [(ロゴの面, 隣のオレンジの面)]


def paint_logos_flat():
    """STEP1 のあと、ロゴの面の塗り分けの色を隣のオレンジの面と同じにする。
    材質を塗り替えただけでは、文字の面が別の島のまま線が残った。"""
    import numpy as np
    for name, comps in LOGO.items():
        me = bpy.data.objects[name].data
        for ca in me.color_attributes:
            if ca.domain != "CORNER":
                continue
            buf = np.empty(len(ca.data) * 4, dtype=np.float32)
            ca.data.foreach_get("color", buf)
            buf = buf.reshape(-1, 4)
            # 文字は外装と一続きの面に、くぼみの輪郭として作られていて、黒い面だけ
            # 塗り直しても縁で線が出た。近い文字を1つのロゴにまとめ、その外枠を
            # 広げた範囲の面を全部、すぐ外側の輪で一番多い色にする(文字ごとに
            # 別の色で塗ると四角い跡と切れ端が残った)
            cen = np.empty(len(me.polygons) * 3, dtype=np.float32)
            me.polygons.foreach_get("center", cen)
            cen = cen.reshape(-1, 3)
            boxes = [[np.array(mn), np.array(mx)] for _, _, mn, mx in comps]
            merged = True
            while merged:
                merged = False
                for a in range(len(boxes)):
                    for b in range(a + 1, len(boxes)):
                        (a0, a1), (b0, b1) = boxes[a], boxes[b]
                        if np.all(a0 - 0.1 <= b1) and np.all(b0 - 0.1 <= a1):
                            boxes[a] = [np.minimum(a0, b0), np.maximum(a1, b1)]
                            boxes.pop(b)
                            merged = True
                            break
                    if merged:
                        break
            loop_of = np.array([p.loop_start for p in me.polygons])
            for lo, hi in boxes:
                inner = np.all((cen >= lo - 0.015) & (cen <= hi + 0.015), axis=1)
                outer = np.all((cen >= lo - 0.04) & (cen <= hi + 0.04), axis=1) & ~inner
                ring = np.round(buf[loop_of[outer]], 3)
                if not len(ring):
                    continue
                vals, cnt = np.unique(ring, axis=0, return_counts=True)
                src = vals[np.argmax(cnt)]
                for fi in np.nonzero(inner)[0].tolist():
                    p = me.polygons[fi]
                    buf[p.loop_start:p.loop_start + p.loop_total] = src
            ca.data.foreach_set("color", buf.ravel())
        me.update()


def remove_logos():
    """メーカーのロゴを消す。ロゴはテクスチャではなく、オレンジの外装の中に
    黒(Motor-black)の面として作り込まれていて、線画に「KUKA」と出た。
    オレンジの面だけに囲まれた小さな黒の面のまとまりを、オレンジに塗り替える
    (モーターなど本物の黒い部品は、周りがオレンジだけではないので残る)。"""
    import bmesh
    n_fix = 0
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        names = [m.name if m else "" for m in o.data.materials]
        if "Motor-black" not in names or "Orange-housing" not in names:
            continue
        black, orange = names.index("Motor-black"), names.index("Orange-housing")
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        from mathutils.kdtree import KDTree
        oranges = [f for f in bm.faces if f.material_index == orange]
        kd = KDTree(max(1, len(oranges)))
        for f in oranges:
            kd.insert(f.calc_center_median(), f.index)
        kd.balance()
        seen = set()
        loose = []
        for f in bm.faces:
            if f.material_index != black or f.index in seen:
                continue
            comp, stack, ok = [], [f], True
            seen.add(f.index)
            while stack:
                g = stack.pop()
                comp.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h.index in seen:
                            continue
                        if h.material_index == black:
                            seen.add(h.index)
                            stack.append(h)
                        elif h.material_index != orange:
                            ok = False
            co = [v.co for g in comp for v in g.verts]
            ext = max(max(c[i] for c in co) - min(c[i] for c in co) for i in range(3))
            if ok and ext < 0.35:
                # 隣のオレンジの面(つながっていない文字は、いちばん近いオレンジの面)
                nb = next((h.index for g in comp for e in g.edges for h in e.link_faces
                           if h.material_index == orange), None)
                if nb is None:
                    loose.extend(comp)
                    ctr = sum((g.calc_center_median() for g in comp), Vector()) / len(comp)
                    nb = kd.find(ctr)[1]
                for g in comp:
                    g.material_index = orange
                mn = Vector((min(c[i] for c in co) for i in range(3)))
                mx = Vector((max(c[i] for c in co) for i in range(3)))
                LOGO.setdefault(o.name, []).append(([g.index for g in comp], nb, mn, mx))
                n_fix += len(comp)
        # 形も消す: 浮いた文字は削除、外装と一続きの文字はくぼみを均して平らに。
        # 塗りだけ直すと、陰影に薄く「KUKA」が残った
        boxes = [(mn, mx) for _, _, mn, mx in LOGO.get(o.name, [])]
        if loose:
            bmesh.ops.delete(bm, geom=list({f for f in loose}), context="FACES")
        if boxes:
            pad = 0.015
            sel = [v for v in bm.verts if v.is_valid and any(
                all(lo[i] - pad <= v.co[i] <= hi[i] + pad for i in range(3)) for lo, hi in boxes)]
            for _ in range(80):
                bmesh.ops.smooth_vert(bm, verts=sel, factor=0.5,
                                      use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bm.to_mesh(o.data)
        bm.free()
    print(f"@@@ logo faces recolored: {n_fix}", flush=True)


def build():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    sc = bpy.context.scene
    for o in list(sc.objects):
        if o.type in {"CAMERA", "LIGHT", "FONT"} or o.name.startswith("Transformation-orientation"):
            bpy.data.objects.remove(o, do_unlink=True)
    remove_logos()
    joints()
    measure_grip()
    # 手首の向きの符号: 肩を 20 度振ったとき、グリッパーの向きが変わらない方
    ws = 1.0
    ref = grip_world().to_3x3()
    for s in (1.0, -1.0):
        set_pose(0.0, math.radians(20), 0.0, s)
        d = (grip_world().to_3x3() @ Vector((0, 0, 1))).angle(ref @ Vector((0, 0, 1)))
        if d < math.radians(1.0):
            ws = s
    set_pose(0.0, 0.0, 0.0, ws)
    print(f"@@@ wrist sign {ws}", flush=True)

    env = floor_and_fence()
    pick = [pallet(f"pallet_L{i}") for i in range(N_PICK)]
    place = [pallet(f"pallet_R{i}") for i in range(N_PLACE)]
    for i, o in enumerate(pick):
        o.matrix_world = stack_matrix(YAW_PICK, i)
    for i, o in enumerate(place):
        o.matrix_world = stack_matrix(YAW_PLACE, i)
    carried = pick[-1]
    top_pick = stack_matrix(YAW_PICK, N_PICK - 1).translation
    top_place = stack_matrix(YAW_PLACE, N_PLACE).translation
    up = Vector((0, 0, 0.55))
    poses = {                                     # (yaw, つかむ点)
        "hover_L": (YAW_PICK, top_pick + up),
        "grip_L": (YAW_PICK, top_pick),
        "lift_L": (YAW_PICK, top_pick + up),
        "hover_R": (YAW_PLACE, top_place + up),
        "set_R": (YAW_PLACE, top_place),
    }
    ang = {}
    for k, (yaw, t) in poses.items():
        e, a2, a3 = solve(yaw, t, ws)
        ang[k] = (yaw, math.radians(a2), math.radians(a3))
        print(f"@@@ pose {k}: yaw {math.degrees(yaw):.0f} a2 {a2:.2f} a3 {a3:.2f} err {e * 1000:.1f}mm", flush=True)
    # 時間割(フレーム): 降りる -> つかむ -> 上がる -> 回る -> 降りる -> 放す -> 上がる
    key = [(1, "hover_L"), (40, "grip_L"), (58, "grip_L"), (96, "lift_L"),
           (176, "hover_R"), (214, "set_R"), (232, "set_R"), (270, "hover_R"),
           (FRAMES, "hover_R")]
    clamp = [(1, 0.0), (40, 0.0), (56, -0.9), (214, -0.9), (230, 0.0)]
    lever = J["Clamp.lever"]
    for f, k in key:
        yaw, a2, a3 = ang[k]
        set_pose(yaw, a2, a3, ws)
        for n in ("Link.1", "Link2", "Link.3", "Link.5"):
            J[n].keyframe_insert("rotation_euler", frame=f)
    for f, v in clamp:
        lever.rotation_euler.y = v
        lever.keyframe_insert("rotation_euler", index=1, frame=f)
    # 運ぶパレット: つかんでから放すまで、グリッパーについて行く
    sc.frame_set(58)
    off = grip_world().inverted() @ carried.matrix_world
    for f in range(1, FRAMES + 1):
        if 58 <= f <= 214:
            sc.frame_set(f)
            carried.matrix_world = grip_world() @ off
        elif f < 58:
            carried.matrix_world = stack_matrix(YAW_PICK, N_PICK - 1)
        else:
            continue
        carried.keyframe_insert("location", frame=f)
        carried.keyframe_insert("rotation_euler", frame=f)

    # カメラ: 正面(-y)の少し上から、左へ 50 度回り込む
    cd = bpy.data.cameras.new("C")
    cd.lens = 30.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tgt = Vector((0.0, -0.8, 1.15))
    for f in range(1, FRAMES + 1):
        s = (f - 1) / (FRAMES - 1)
        e = 0.5 - 0.5 * math.cos(s * math.pi)
        a = math.radians(-30.0 + 50.0 * e)
        d = 5.0 - 0.5 * e
        cam.location = (tgt.x + math.sin(a) * d, tgt.y - math.cos(a) * d, 2.2 - 0.4 * e)
        cam.rotation_euler = (tgt - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    lt = bpy.data.objects.new("K", bpy.data.lights.new("K", type="SUN"))
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(50), 0, math.radians(-35))

    sc.frame_start, sc.frame_end = 1, FRAMES
    sc.render.fps = FPS
    sc.render.engine = fp_batch.eevee_engine()
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.frame_set(1)
    meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render
              and len(o.data.polygons) > 0]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    sc.fp_auto_style = 'PRECISE'
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    paint_logos_flat()
    sc.fp_white_preview = True
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = 'MONO_LIGHT'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "kuka.blend"))
    print(f"@@@ built {len(meshes)} meshes", flush=True)


def shoot():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "kuka.blend"))
    sc = bpy.context.scene
    prev = "--preview" in ARGV
    res = int(arg("--res", "960" if prev else "1920"))
    sc.render.resolution_x, sc.render.resolution_y = res, res * 9 // 16
    sc.eevee.taa_render_samples = int(arg("--samples", "4" if prev else "32"))
    d = OUT / arg("--tag", "kuka_preview" if prev else "kuka")
    d.mkdir(parents=True, exist_ok=True)
    if arg("--stills"):
        for f in [int(v) for v in arg("--stills").split(",")]:
            sc.frame_set(f)
            sc.render.filepath = str(d / f"f{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    else:
        sc.render.filepath = str(d / "f")
        bpy.ops.render.render(animation=True)
    print(f"@@@ shot {d}", flush=True)


if __name__ == "__main__":
    if "--build" in ARGV:
        build()
    else:
        shoot()
