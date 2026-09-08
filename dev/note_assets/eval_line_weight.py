"""アドオンに入れた「線の強弱(くぼみ)」を、実機で前後比較する。

画像の上で試した手順ではなく、アドオンが組んだノードで出した絵を見る。
手順は使う人と同じ。

    STEP0 -> しきい値を測る(1回) -> 強弱ON -> STEP3 -> レンダ

出すもの: off.png / on.png と、その .blend

  blender -b --factory-startup --python eval_line_weight.py -- \
      --out <dir> [--model suzanne|<pattern>] [--res 1920]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "lw"))).resolve()
RES_W = int(arg("--res", "1920"))
MODEL = arg("--model", "suzanne")
VIEW_DEG = float(arg("--view", "20"))
STRENGTH = float(arg("--strength", "1.0"))
MERGE = float(arg("--merge", "0.3"))
RIDGE = float(arg("--ridge", "0.25"))
# 指定が無ければ v2.7 の既定(0.5)。スザンヌだけは土台の掃き出しで
# 決めた 0.25 を使う
SENS = arg("--sens")
SUBDIV = int(arg("--subdiv", "2"))
# None は自動判定。数値ならその角度で固定
ANGLE = arg("--angle")
RELIEF = float(arg("--relief", "0.0"))
RELIEF_R = float(arg("--relief-radius", "6"))
RELIEF_TH = float(arg("--relief-th", "0.35"))
# 指定が無ければアドオンの既定に任せる。ここで 0 を入れてしまい、
# 既定を変えたのに絵が1ビットも変わらないことがあった
CROWD = arg("--crowd")
CROWD_R = arg("--crowd-radius")
CROWD_TH = arg("--crowd-th")
ISLAND = arg("--island-bias")
LINEB = arg("--line-bias")

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W), "--ss", "1"]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def build():
    if MODEL == "suzanne":
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_monkey_add()
        o = bpy.context.object
        if SUBDIV > 0:
            m = o.modifiers.new("Subdivision", "SUBSURF")
            m.levels = m.render_levels = SUBDIV
            bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.ops.object.shade_smooth()
        return [o]
    blend = dm.find_blend(MODEL)
    if blend is None:
        raise SystemExit(f"見つからない: {MODEL}")
    meshes, _ = dm.load(blend)
    return meshes


def stage(meshes):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes
           for c in o.bound_box if not o.hide_render]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    center = Vector(((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5,
                     (min(zs) + max(zs)) * 0.5))
    r = max((p - center).length for p in pts)
    cd = bpy.data.cameras.new("C")
    cd.lens = 55.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(VIEW_DEG)

    def place(d):
        cam.location = (center.x + math.sin(a) * d, center.y - math.cos(a) * d,
                        center.z + d * 0.14)
        cam.rotation_euler = (center - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    from bpy_extras.object_utils import world_to_camera_view
    dist = r * 3.0
    for _ in range(3):
        place(dist)
        m = max(max(abs(world_to_camera_view(sc, cam, p).x - 0.5) * 2.0,
                    abs(world_to_camera_view(sc, cam, p).y - 0.5) * 2.0)
                for p in pts)
        dist *= m * 1.10
    place(dist)
    cd.clip_end = dist * 30

    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1.0)
        bg.inputs[1].default_value = 0.15
    sc.world = w
    lt = bpy.data.lights.new("Key", type="SUN")
    lt.energy = 3.0
    lt.angle = 0.0
    key = bpy.data.objects.new("Key", lt)
    sc.collection.objects.link(key)
    key.rotation_euler = (math.radians(62), 0.0, math.radians(40) + a)
    return r


def main() -> None:
    fp_batch.install_addon()
    meshes = build()
    dm.grey(meshes)
    r = stage(meshes)

    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    # 細線化は強弱の前提。太らせてから 50% 縮小する。
    # ただしアドオン側の細線化(200%レンダ + Scale 0.5)は、キャンバスは
    # レンダー解像度のままで中身だけが半分になるので、そのまま保存すると
    # 黒い額縁の中に小さい絵が入る。ここでは 2倍でレンダして保存時に
    # 縮小する(render_still の ss)。手順としては同じ
    sc.fp_auto_supersample = False
    if MODEL == "suzanne":
        sc.fp_auto_merge = False
        sc.fp_auto_sharp = False
        sc.fp_sharp_auto = ANGLE is None
        if ANGLE is not None:
            sc.fp_sharp_edges = float(ANGLE)
        sc.fp_min_island_area_pct = MERGE
        sc.fp_ridge_amount = RIDGE
        sc.fp_ridge_radius = 0.08
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    if SENS is not None:
        sc.fp_line_sensitivity = float(SENS)
    elif MODEL == "suzanne":
        sc.fp_line_sensitivity = 0.25

    sc.fp_far_relief = RELIEF
    sc.fp_far_relief_radius = RELIEF_R
    sc.fp_far_relief_threshold = RELIEF_TH
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.fp_supersample = False
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W * 2
    sc.render.resolution_y = RES_H * 2
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    say(f"STEP0 済み。解像度 {sc.render.resolution_percentage}%")

    # 強弱なし
    fp_batch.render_still(sc, OUT / "off.png", 2)
    say("off.png")

    # くぼみの半径はモデルの大きさに合わせる
    sc.fp_lw_ao_dist = r * 0.6
    sc.fp_lw_strength = STRENGTH
    if CROWD is not None:
        sc.fp_lw_crowd = float(CROWD)
    if CROWD_R is not None:
        sc.fp_lw_crowd_radius = int(CROWD_R)
    if CROWD_TH is not None:
        sc.fp_lw_crowd_threshold = float(CROWD_TH)
    if ISLAND is not None:
        sc.fp_lw_island_bias = float(ISLAND)
    if LINEB is not None:
        sc.fp_lw_line_bias = float(LINEB)
    sc.fp_line_weight = True

    # 島を切る細かさは STEP1 で決まるので、強弱をONにしてから
    # STEP0 をやり直す。STEP3 だけでは反映されない
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    if SENS is not None:
        sc.fp_line_sensitivity = float(SENS)
    elif MODEL == "suzanne":
        sc.fp_line_sensitivity = 0.25

    # しきい値を1回測る。ここは使う人がボタンを押すのと同じ
    res = bpy.ops.freepencil.measure_line_weight()
    edges = [round(getattr(sc, f"fp_lw_e{i}"), 5) for i in range(1, 5)]
    say(f"計測 {res}  段の境目 {edges}")

    bpy.ops.freepencil2.link_button()   # STEP3
    sc.fp_white_preview = True
    fp_batch.render_still(sc, OUT / "on.png", 2)
    say("on.png")

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "lw.blend"))
    (OUT / "lw.json").write_text(json.dumps(
        {"model": MODEL, "res": [RES_W, RES_H], "radius": round(r, 4),
         "edges": edges, "strength": STRENGTH, "merge": MERGE,
         "ridge": RIDGE, "sens": sc.fp_line_sensitivity, "subdiv": SUBDIV, "angle": ANGLE,
         "relief": RELIEF, "relief_radius": RELIEF_R, "crowd": sc.fp_lw_crowd,
         "crowd_radius": sc.fp_lw_crowd_radius,
         "crowd_threshold": sc.fp_lw_crowd_threshold,
         "ao_dist": round(sc.fp_lw_ao_dist, 4),
         "island_bias": sc.fp_lw_island_bias,
         "line_bias": sc.fp_lw_line_bias},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
