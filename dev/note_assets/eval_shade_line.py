"""陰影の境目を線として足す実験。まず球で確かめる。

球はなめらかなので、いまの仕組みでは輪郭しか線が出ない。そこへ
「光と影の境目(ターミネータ)」を線として足せるかを見る。

絵としての良し悪しは一旦おいて、次の3つだけを確かめる。
    ・境目の線が1本きれいに出るか
    ・しきい値を変えると線がどう動くか
    ・段を増やす(明部/中間/暗部)と線が2本になるか

出すもの:
    line.png    いまの線画
    shade.png   陰影のみ(仮想ライト1灯)
    plain.png   同上(白プレビュー無し)

合成は eval_shade_mix.py が画像の上で行う。効くと分かってから
ノードに入れる。

  blender -b --factory-startup --python eval_shade_line.py -- \
      --out <dir> [--model sphere|<pattern>] [--res 1600] [--light 40]
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
OUT = Path(arg("--out", str(HERE / "out" / "shade"))).resolve()
RES_W = int(arg("--res", "1600"))
MODEL = arg("--model", "sphere")
LIGHT_DEG = float(arg("--light", "40"))
ELEV_DEG = float(arg("--elev", "70"))
# 方位角をまとめて撮る。"-60,-30,0,30,60" のように渡す
SWEEP = arg("--sweep")

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W), "--ss", "1"]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def build_sphere():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=96,
                                         ring_count=48)
    o = bpy.context.object
    bpy.ops.object.shade_smooth()
    return [o]


def stage_one_light(meshes):
    """カメラと、方向のはっきりした1灯。影の境目を見たいので1灯だけ。

    dm.stage は2灯(キー+フィル)なので境目がぼやける。ここでは使わない。
    """
    from mathutils import Vector
    sc = bpy.context.scene
    pts = []
    for o in meshes:
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    xs = [p.x for p in pts]
    zs = [p.z for p in pts]
    cz = (min(zs) + max(zs)) * 0.5
    r = max(max(xs) - min(xs), max(zs) - min(zs)) * 0.5
    lens = 55.0
    # 横幅だけで距離を決めると、16:9 では縦がはみ出して球が上下で切れる。
    # 縦のセンサー幅でも計算して、遠い方を採る
    sensor_w = 36.0
    sensor_h = sensor_w * RES_H / RES_W
    margin = 1.35
    dist = max(r * margin / math.tan(math.atan(sensor_w * 0.5 / lens)),
               r * margin / math.tan(math.atan(sensor_h * 0.5 / lens)))
    cd = bpy.data.cameras.new("C")
    cd.lens = lens
    cd.clip_end = dist * 20
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.0, -dist, cz)
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)

    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1.0)
        bg.inputs[1].default_value = 0.15   # 環境光は弱く。境目を立たせる
    sc.world = w
    lt = bpy.data.lights.new("Key", type="SUN")
    lt.energy = 3.0
    lt.angle = 0.0                          # 影の縁をぼかさない
    lo = bpy.data.objects.new("Key", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(ELEV_DEG), 0.0,
                         math.radians(LIGHT_DEG))
    return lo


def main() -> None:
    fp_batch.install_addon()
    if MODEL == "sphere":
        meshes = build_sphere()
    else:
        blend = dm.find_blend(MODEL)
        if blend is None:
            raise SystemExit(f"見つからない: {MODEL}")
        meshes, _ = dm.load(blend)
    dm.grey(meshes)
    key = stage_one_light(meshes)

    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    say(f"STEP0 {time.time() - t:.1f}秒 / メッシュ {len(meshes)}")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 64
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    # 線は光に依存しないので一度だけ撮る
    sc.use_nodes = True
    fp_batch.render_still(sc, OUT / "line.png", 1)
    sc.use_nodes = False
    sc.fp_white_preview = False
    if SWEEP:
        for a in [float(x) for x in SWEEP.split(",")]:
            key.rotation_euler = (math.radians(ELEV_DEG), 0.0, math.radians(a))
            bpy.context.view_layer.update()
            fp_batch.render_still(sc, OUT / f"shade_{int(a):+04d}.png", 1)
            say(f"  shade {a:+.0f}度")
    else:
        fp_batch.render_still(sc, OUT / "shade.png", 1)
    say("  line.png / shade")

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "shade.blend"))
    (OUT / "shade.json").write_text(json.dumps(
        {"model": MODEL, "light_deg": LIGHT_DEG, "res": [RES_W, RES_H]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
