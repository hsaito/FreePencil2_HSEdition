"""ロゴの線だけを、動画を作らずに検証する。

make_showcase_movie.py は 400万面のシーンを組んで STEP0 に 40秒、1フレーム
12秒かかる。ロゴの形と線を詰めるだけなら、そこを毎回やり直す理由がない。
このスクリプトはロゴと背景の壁・床・照明だけを置き、本番のラストカットと
同じ画角・同じプレビュー設定で描く。1本あたり十数秒で回る。

本番と揃えているもの:
  - 文字の作り方(押し出し・平面チャンファー・曲線分割・痩せ)
  - 手動しきい値での塗り直し(自動だと85度=42島になり線が出ない)
  - MONO_LIGHT プレビューと floor
  - 横へ回り込んで見上げるカメラ
  - スーパーサンプリング(等倍レンダ→箱縮小。アドオン側の細線化は使わない)

    blender -b --factory-startup --python eval_logo.py -- \
        [--deg 20] [--ru 8] [--extrude 0.70] [--bevel 0.035] [--tag base]

--zoom x0,y0,x1,y1 で切り出し倍率3倍の拡大も併せて保存する。
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "logo_eval"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
TAG = arg("--tag", "base")
RES = int(arg("--res", "1920"))
SS = int(arg("--ss", "2"))
DEG = float(arg("--deg", "20.0"))
RU = int(arg("--ru", "8"))
EXTRUDE = float(arg("--extrude", "0.70"))
BEVEL = float(arg("--bevel", "0.035"))
OFFSET = float(arg("--offset", "-0.004"))
FLOOR = float(arg("--floor", "0.25"))
HEIGHT = float(arg("--height", "3.2"))
HALL_W = float(arg("--hall-w", "7.5"))
HALL_H = float(arg("--hall-h", "6.0"))
SIDE = float(arg("--side", "4.2"))      # 横へ回り込む量
PED_H = 0.5
ZOOM = arg("--zoom", "250,380,760,700")
CLEAR_Y = float(arg("--clear", "16.0"))       # ロゴ手前の柱を抜く範囲(m)
CLEAR_BACK = float(arg("--clear-back", "8.0"))  # ロゴ奥の柱を抜く範囲(m)
TRACK = float(arg("--track", "1.0"))      # 字間(1.0で標準)
AOV = "--aov" in ARGV                     # 塗り分けの生の色も書き出す
TURN = int(arg("--turn", "0"))            # >0 ならロゴを1回転させて動画にする
FPS = int(arg("--fps", "15"))
NO_ROOM = "--no-room" in ARGV             # ロゴだけ見たいときはホールを省く
LOGO_SEED = int(arg("--logo-seed", "-1"))  # >=0 でロゴだけ別のパレットにする
PREVIEW = arg("--preview", "MONO_LIGHT")   # NONE / WHITE / MONO_LIGHT
VC = "--vc" in ARGV                        # 頂点カラーを素通しで描く
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def build_logo():
    cur = bpy.data.curves.new("LogoText", type="FONT")
    cur.body = "FreePencil2"
    cur.align_x = "CENTER"
    cur.align_y = "BOTTOM"
    cur.extrude = EXTRUDE
    cur.bevel_depth = BEVEL
    cur.bevel_resolution = 0     # 平面の面取り。丸めると線が消える(実測)
    cur.offset = OFFSET
    cur.resolution_u = RU
    cur.space_character = TRACK   # "cil2" が詰まって読めないので少し開ける
    o = bpy.data.objects.new("FP_LOGO", cur)
    bpy.context.scene.collection.objects.link(o)
    o.rotation_euler = (math.radians(90), 0.0, math.radians(180))
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    o = bpy.context.object

    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    k = HEIGHT / max(mx.z - mn.z, 1e-6)
    k = min(k, HALL_W * 2.0 * 0.78 / max(mx.x - mn.x, 1e-6))
    o.scale = (k, k, k)
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn2 = Vector((min(p[i] for p in pts) for i in range(3)))
    mx2 = Vector((max(p[i] for p in pts) for i in range(3)))
    o.location = (0.0, 0.0, PED_H + 0.6 - mn2.z)
    bpy.context.view_layer.update()
    say(f"ロゴ {len(o.data.polygons):,}面 / 幅 {mx2.x - mn2.x:.1f}m")
    return o, mx2.x - mn2.x


def box(name, loc, scale):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object
    o.name = name
    o.location = loc
    o.scale = scale
    return o


def build_room():
    """本番の突き当たり付近だけを作る。奥行きは画角に入る分でよい。"""
    W, H = HALL_W, HALL_H
    box("FLOOR", (0.0, 12.0, -0.05), (60.0, 60.0, 0.1))
    box("ENDWALL", (0.0, -6.0, H * 0.5), (W * 2, 0.6, H))
    box("ENDBAND", (0.0, -5.7, H * 0.66), (W * 1.5, 0.5, 1.4))
    box("CEIL", (0.0, 12.0, H + 0.3), (W * 2, 60.0, 0.6))
    for side in (-1, 1):
        box(f"WALL_{side}", (side * W, 12.0, H * 0.5), (0.6, 60.0, H))
        box(f"WALLBAND_{side}", (side * (W - 0.7), 12.0, H * 0.62),
            (0.5, 60.0, 1.1))
        box(f"WALLBASE_{side}", (side * (W - 0.5), 12.0, 0.45),
            (0.7, 60.0, 0.9))
    for i in range(4):
        y = -2.0 + i * 9.0
        box(f"BEAM_{i}", (0.0, y, H - 0.35), (W * 2, 0.55, 0.7))
        # ロゴの前後は柱を立てない。手前に立つとカメラとロゴの間に入り、
        # 奥に立つと文字の隙間から覗いて、どちらも F と il2 を縦に横切る
        if -CLEAR_BACK < y < CLEAR_Y:
            continue
        for side in (-1, 1):
            box(f"COL_{i}_{side}", (side * (W - 1.8), y, H * 0.5),
                (0.7, 0.7, H))


def add_light(px, py, watts, size, shadow=True):
    d = bpy.data.lights.new(f"A_{px:.0f}_{py:.0f}", type="AREA")
    d.energy = watts
    d.shape = "RECTANGLE"
    d.size = size
    d.size_y = size
    d.use_shadow = shadow
    lt = bpy.data.objects.new(d.name, d)
    bpy.context.scene.collection.objects.link(lt)
    lt.location = (px, py, HALL_H - 1.3)
    return lt


def build_room_and_logo():
    logo, logo_w = build_logo()
    if NO_ROOM:
        # ロゴだけを見たいとき。床だけ残して、正面から回して確かめる
        box("FLOOR", (0.0, 0.0, -0.05), (60.0, 60.0, 0.1))
        add_light(0.0, 2.0, 700.0, 8.0)
        add_light(-5.0, 6.0, 300.0, 8.0, shadow=False)
        add_light(5.0, 6.0, 300.0, 8.0, shadow=False)
    else:
        build_room()
        add_light(0.0, 0.0, 560.0, 6.0)
        for i in range(4):
            add_light(0.0, 2.0 + i * 6.75, 260.0, HALL_W * 1.6, shadow=False)
    return logo, logo_w


def render_vertex_colors(scene, png):
    """頂点カラーをそのまま描く。塗り分けの生の結果を目で確かめるため。

    mecha_color の AOV はノードグループの中で
      頂点カラー -> Mix.002(line_texture と混合) -> Mix.005(Generated座標の
      X を Factor にして更に混合) -> AOV 出力
    と2段の Mix を通る。だから AOV を見ても「塗り分けがどうなっているか」は
    分からない。ここでは Attribute -> Emission で頂点カラーを素通しにする。
    """
    mat = bpy.data.materials.new("FP_DEBUG_VC")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "mecha_color"
    em = nt.nodes.new("ShaderNodeEmission")
    ou = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])

    saved = {}
    for o in scene.objects:
        if o.type != "MESH":
            continue
        saved[o.name] = [s.material for s in o.material_slots]
        if not o.material_slots:
            o.data.materials.append(mat)
        else:
            for s in o.material_slots:
                s.material = mat

    # コンポジタを通すと線が乗ってしまうので切る。色変換も素通しにする
    keep_comp = scene.use_nodes
    keep_view = scene.view_settings.view_transform
    scene.use_nodes = False
    scene.view_settings.view_transform = 'Standard'
    fp_batch.render_still(scene, png, SS)
    scene.use_nodes = keep_comp
    scene.view_settings.view_transform = keep_view

    for o in scene.objects:
        if o.type != "MESH" or o.name not in saved:
            continue
        for s, m in zip(o.material_slots, saved[o.name]):
            s.material = m
    say(f"頂点カラー {png}")


def add_camera(logo_w, logo=None):
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 35.0
    cd.clip_end = 800.0
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    half = math.atan(0.5 * cd.sensor_width / cd.lens)
    dist = max((logo_w * 0.5 * 1.18) / math.tan(half), 10.35)

    if TURN > 0 and logo is not None:
        # 回転させると注視点がずれて画面下に沈む。ロゴの実際の中心を見る。
        # また回っている間ずっと収まるよう、幅ではなく「対角」で距離を取る
        pts = [logo.matrix_world @ Vector(c) for c in logo.bound_box]
        mn = Vector((min(p[i] for p in pts) for i in range(3)))
        mx = Vector((max(p[i] for p in pts) for i in range(3)))
        cz = (mn.z + mx.z) * 0.5
        span = math.hypot(mx.x - mn.x, mx.y - mn.y)
        dist = (span * 0.5 * 1.15) / math.tan(half)
        cam.location = (SIDE, dist, cz + (mx.z - mn.z) * 0.35)
        look = Vector((0.0, 0.0, cz))
        say(f"回転カメラ 距離 {dist:.1f}m / 注視 z={cz:.2f} / 対角 {span:.1f}m")
    else:
        cam.location = (SIDE, dist, 1.4)
        look = Vector((0.0, 0.0, PED_H + 1.9))
        say(f"カメラ 距離 {dist:.1f}m / 横 {SIDE}m")
    d = look - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def main():
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene

    logo, logo_w = build_room_and_logo()

    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = PREVIEW
    scene.fp_mono_floor = FLOOR
    # 細線化は使わない。アドオンの 200%+Scale0.5 に箱縮小を重ねると絵ごと
    # 半分に縮んで線が灰色に潰れる(本番スクリプトと同じ扱い)
    scene.fp_auto_supersample = False
    scene.fp_supersample = False

    meshes = [o for o in scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    scene.fp_preview_mode = PREVIEW

    # ロゴだけ手動しきい値で塗り直す(自動は85度=42島で線が出ない)。
    #
    # 同時に色の種も変える。パレットは build_palette(色クラス数, 種, 輝度窓)
    # で作られ、オブジェクトごとの種を持たない。だから色クラス数が同じ
    # オブジェクトは同じパレットになり、実測では壁と F の前面がどちらも
    # 同じ黄緑、r の前面と右の壁がどちらも同じピンクになっていた。
    # 文字と壁の境界に色差が無く、輪郭は深度チャンネルだけが支えていた
    scene.fp_sharp_auto = False
    scene.fp_sharp_edges = DEG
    if LOGO_SEED >= 0:
        scene.fp_color_seed = LOGO_SEED
    bpy.ops.object.select_all(action="DESELECT")
    logo.select_set(True)
    bpy.context.view_layer.objects.active = logo
    bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")
    say(f"ロゴを {DEG}度 で塗り直した")

    add_camera(logo_w, logo)
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 32
    if hasattr(scene.eevee, "shadow_pool_size"):
        scene.eevee.shadow_pool_size = '1024'
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = RES * SS
    scene.render.resolution_y = int(RES * 9 / 16) * SS
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    if AOV:
        # 塗り分けの生の色(mecha_color)をそのまま書き出す。線が出ない箇所が
        # 「隣が似た色だから」なのかを目で確かめるため
        from freepencil2 import compat
        tree = compat.get_compositor_tree(scene, create=True)
        rl = next((n for n in tree.nodes if n.type == "R_LAYERS"), None)
        # compat.render_layer_socket はパスの別名解決用(DiffDir→Diffuse
        # Direct など)で、AOV 名は扱わない。名前で直接引く
        src = next((s for s in rl.outputs
                    if s.name == "mecha_color" and s.enabled), None) if rl \
            else None
        if src is None:
            say("mecha_color ソケットが見つからない")
        else:
            fo = compat.new_node(tree, "CompositorNodeOutputFile")
            fo.base_path = str(OUT)
            fo.file_slots.clear()
            fo.file_slots.new(f"{TAG}_aov_")
            fo.format.file_format = 'OPEN_EXR'
            fo.format.color_depth = '32'
            tree.links.new(src, fo.inputs[0])
            # 深度も出す。深度の段差 = 別の物体が画面で重なっている箇所で、
            # そこに色差が無ければ線が出ない。陰影に埋もれずに判定できる
            dep = next((s for s in rl.outputs
                        if s.name in ("Depth", "Z") and s.enabled), None)
            if dep is not None:
                fo.file_slots.new(f"{TAG}_depth_")
                tree.links.new(dep, fo.inputs[1])
            say("mecha_color と深度を書き出す")

    if TURN > 0:
        # ロゴを1回転させる。カメラを回すと壁や柱が横切るので、回すのは
        # ロゴ側。正面→側面→背面と、面取りと側面の線を全部見せる
        frames = OUT / f"{TAG}_turn"
        frames.mkdir(parents=True, exist_ok=True)
        paths = []
        t0 = time.time()
        # 文字は (X=90, Z=180) で立てている。回すときに rotation_euler を
        # そのまま上書きすると X=90 が消えて床に寝てしまう。Z だけ足す
        rx, ry, rz = logo.rotation_euler
        for i in range(TURN):
            logo.rotation_euler = (rx, ry, rz + 2.0 * math.pi * i / TURN)
            bpy.context.view_layer.update()
            p = frames / f"t{i:03d}.png"
            fp_batch.render_still(scene, p, SS)
            paths.append(p)
            if (i + 1) % 12 == 0 or i + 1 == TURN:
                say(f"  {i + 1}/{TURN} ({time.time() - t0:.0f}s)")
        mp4 = OUT / f"{TAG}_turn.mp4"
        fp_batch.encode_video(paths, mp4, FPS, RES, int(RES * 9 / 16))
        say(f"回転動画 {mp4} ({mp4.stat().st_size // 1024} KB)")
        return

    if VC:
        render_vertex_colors(scene, OUT / f"{TAG}_vc.png")

    png = OUT / f"{TAG}.png"
    fp_batch.render_still(scene, png, SS)

    im = bpy.data.images.load(str(png))
    w, h = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]
    g = a[:, :, :3].mean(axis=2)
    say(f"{TAG}: {w}x{h} 平均={g.mean():.4f} 最小={g.min():.3f} "
        f"ink={float((g < 0.5).mean()):.4f} 黒={float((g < 0.15).mean()):.4f}")

    if ZOOM:
        x0, y0, x1, y1 = (int(v) for v in ZOOM.split(","))
        crop = a[y0:y1, x0:x1]
        big = np.repeat(np.repeat(crop, 3, axis=0), 3, axis=1)
        cg = big[:, :, :3].mean(axis=2)
        say(f"拡大域: ink={float((cg < 0.5).mean()):.4f} "
            f"黒={float((cg < 0.15).mean()):.4f}")
        out = bpy.data.images.new("zoom", big.shape[1], big.shape[0],
                                  alpha=True)
        out.pixels = big[::-1].ravel().tolist()
        zp = OUT / f"{TAG}_zoom.png"
        out.filepath_raw = str(zp)
        out.file_format = 'PNG'
        out.save()
        say(f"拡大 {zp}")
    bpy.data.images.remove(im)
    say(f"完了 {png}")


if __name__ == "__main__":
    main()
