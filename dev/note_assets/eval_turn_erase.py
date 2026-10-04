"""スザンヌを回して、光による線の抜きが安定するかを見る。

これが実用可否を分ける。抜ける場所は光で決まるので、カメラを回すと
モデル上で抜き位置が動く。それが「線が波打つ」ように見えないか。

光の付け方を2通り撮って比べる。

    world   光を世界に固定する。物理的に正しい。回すと抜きがモデル上を移動
    camera  光をカメラに追従させる。画面上で抜き位置が動かない

線は光に依存しないので1フレームにつき1枚。陰影は2通り撮る。

  blender -b --factory-startup --python eval_turn_erase.py -- \
      --out <dir> [--frames 72] [--res 1600] [--turn 350]
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
OUT = Path(arg("--out", str(HERE / "out" / "turn_erase"))).resolve()
RES_W = int(arg("--res", "1600"))
FRAMES = int(arg("--frames", "72"))
TURN = float(arg("--turn", "350"))
SUBDIV = int(arg("--subdiv", "2"))
# 光の向き。カメラ追従のときは、この値がカメラからの相対角になる
LIGHT_AZ = float(arg("--light", "40"))
LIGHT_EL = float(arg("--elev", "62"))

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
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    if SUBDIV > 0:
        m = o.modifiers.new("Subdivision", "SUBSURF")
        m.levels = m.render_levels = SUBDIV
        bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    return [o]


def stage(meshes):
    """カメラと1灯。カメラは周回、光は毎フレーム置き直す。"""
    sc = bpy.context.scene
    pts = []
    for o in meshes:
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    center = Vector(((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5,
                     (min(zs) + max(zs)) * 0.5))
    # 回すので水平方向の外接円で見る。切れないように
    r = max(math.hypot(p.x - center.x, p.y - center.y) for p in pts)
    h = (max(zs) - min(zs)) * 0.5
    lens = 55.0
    sw = 36.0
    sh = sw * RES_H / RES_W
    dist = max(r * 1.3 / math.tan(math.atan(sw * 0.5 / lens)),
               h * 1.3 / math.tan(math.atan(sh * 0.5 / lens)))
    cd = bpy.data.cameras.new("C")
    cd.lens = lens
    cd.clip_end = dist * 30
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam

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
    return cam, key, center, dist


def main() -> None:
    fp_batch.install_addon()
    meshes = build()
    dm.grey(meshes)
    cam, key, center, dist = stage(meshes)

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
    say(f"STEP0 {time.time() - t:.1f}秒")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    for d in ("line", "shade_world", "shade_camera"):
        (OUT / d).mkdir(parents=True, exist_ok=True)

    t = time.time()
    for f in range(FRAMES):
        a = math.radians(TURN * f / max(FRAMES - 1, 1))
        cam.location = (center.x + math.sin(a) * dist,
                        center.y - math.cos(a) * dist,
                        center.z + dist * 0.14)
        look = center - Vector(cam.location)
        cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()

        # 線は光に依存しない。1枚だけ
        sc.use_nodes = True
        sc.fp_white_preview = True
        fp_batch.render_still(sc, OUT / "line" / f"f{f:04d}.png", 1)

        sc.use_nodes = False
        sc.fp_white_preview = False
        # 世界に固定
        key.rotation_euler = (math.radians(LIGHT_EL), 0.0,
                              math.radians(LIGHT_AZ))
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, OUT / "shade_world" / f"f{f:04d}.png", 1)
        # カメラに追従。カメラの周回角を足す
        key.rotation_euler = (math.radians(LIGHT_EL), 0.0,
                              math.radians(LIGHT_AZ) + a)
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, OUT / "shade_camera" / f"f{f:04d}.png", 1)

        if (f + 1) % 12 == 0:
            say(f"  {f + 1}/{FRAMES} ({time.time() - t:.0f}s)")

    (OUT / "turn.json").write_text(json.dumps(
        {"frames": FRAMES, "turn": TURN, "res": [RES_W, RES_H],
         "light": [LIGHT_AZ, LIGHT_EL]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
