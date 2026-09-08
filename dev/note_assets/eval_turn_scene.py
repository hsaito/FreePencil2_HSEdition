"""たくさん並べたシーンをカメラで回し、線の太さの変化を見る。

静止画で良く見えても、回したときにフレームごとに太さがちらつけば
アニメには使えない。発見した規則(線が疎なら太く、密なら細く)が
時間方向に安定しているかを確かめるための素材を撮る。

配置について:
    fp_batch.normalize はオブジェクトを原点に寄せない。location を
    足すやり方では動かないものがあり、3体が x=14/30/32 に散った。
    ここでは matrix_world を直接ずらす。これなら親子関係に関係なく効く。

回転について:
    オブジェクトを回すと親子付けが要る。カメラを回せばシーンには
    一切触らずに済むので、そうする。

  blender -b --factory-startup --python eval_turn_scene.py -- \
      --out <dir> [--frames 48] [--res 1200]
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
OUT = Path(arg("--out", str(HERE / "out" / "turn"))).resolve()
FRAMES = int(arg("--frames", "48"))
RES_W = int(arg("--res", "1200"))
SS = 1

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W),
            "--ss", str(SS)]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
from mathutils import Vector, Matrix   # noqa: E402
import fp_batch                   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()

# 密度の差が出るように、細かい物と大きい物を混ぜる
MODELS = [
    "toy_train-02*", "portable-generat*", "space_scavenger*",
    "arched_hangar*", "japan-apartment*", "halloween_pumpki*",
]


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def bounds(objs):
    pts = []
    for o in objs:
        if o.type != "MESH" or o.hide_render:
            continue
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        return None
    return (Vector((min(p.x for p in pts), min(p.y for p in pts),
                    min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts),
                    max(p.z for p in pts))))


def move(objs, delta: Vector) -> None:
    """グループを平行移動する。

    location を足すやり方では、親を持つものが動かず配置が壊れた。
    matrix_world を直接書き換えれば、親子関係によらず必ず動く。
    """
    group = set(objs)
    for o in objs:
        if o.parent in group:
            continue          # 親が一緒に動くので触らない
        o.matrix_world = Matrix.Translation(delta) @ o.matrix_world
    bpy.context.view_layer.update()


def place(pattern: str):
    blend = dm.find_blend(pattern)
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
    fp_batch.normalize(meshes + others,
                       [o for o in content if o in cluster] or content)
    bpy.context.view_layer.update()
    return meshes + others


def main() -> None:
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)

    # 3列 x 2行で並べる。前後にもずらして重なりを作る
    meshes = []
    step = 2.6
    for i, pat in enumerate(MODELS):
        objs = place(pat)
        if not objs:
            continue
        b = bounds(objs)
        if b is None:
            continue
        center = (b[0] + b[1]) * 0.5
        col, row = i % 3, i // 3
        target = Vector(((col - 1) * step, (row - 0.5) * step * 0.9,
                         -b[0].z + center.z))
        move(objs, Vector((target.x - center.x, target.y - center.y,
                           -b[0].z)))
        nb = bounds(objs)
        say(f"{pat[:18]:<18} -> x {nb[0].x:6.2f}..{nb[1].x:6.2f} "
            f"y {nb[0].y:6.2f} z {nb[0].z:5.2f}..{nb[1].z:5.2f}")
        meshes += [o for o in objs if o.type == "MESH"]
    if not meshes:
        raise SystemExit("配置できなかった")

    dm.grey(meshes)
    b = bounds(meshes)
    center = (b[0] + b[1]) * 0.5
    radius = max((b[1] - b[0]).x, (b[1] - b[0]).y) * 0.5
    height = (b[1] - b[0]).z

    sc = bpy.context.scene
    lens = 50.0
    sensor_w = 36.0
    sensor_h = sensor_w * RES_H / RES_W
    dist = max(radius * 1.25 / math.tan(math.atan(sensor_w * 0.5 / lens)),
               height * 0.62 / math.tan(math.atan(sensor_h * 0.5 / lens)))
    cd = bpy.data.cameras.new("C")
    cd.lens = lens
    cd.clip_end = dist * 30
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    say(f"シーン: 半径 {radius:.2f} 高さ {height:.2f} カメラ距離 {dist:.2f}")

    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1.0)
        bg.inputs[1].default_value = 0.5
    sc.world = w
    lt = bpy.data.lights.new("Key", type="SUN")
    lt.energy = 3.5
    lo = bpy.data.objects.new("Key", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(55), 0.0, math.radians(35))

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
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    sc.use_nodes = True

    d = OUT / "line"
    d.mkdir(parents=True, exist_ok=True)
    t = time.time()
    for f in range(FRAMES):
        ang = math.radians(-28.0 + 56.0 * f / max(FRAMES - 1, 1))
        cam.location = (center.x + math.sin(ang) * dist,
                        center.y - math.cos(ang) * dist,
                        center.z + dist * 0.16)
        look = center - Vector(cam.location)
        cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, d / f"f{f:04d}.png", SS)
        if (f + 1) % 12 == 0:
            say(f"  {f + 1}/{FRAMES} ({time.time() - t:.0f}s)")

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "turn.blend"))
    (OUT / "turn.json").write_text(json.dumps(
        {"frames": FRAMES, "res": [RES_W, RES_H],
         "models": MODELS}, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
