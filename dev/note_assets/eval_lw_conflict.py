"""強弱(2値化)が既存機能を無効にしていないかを棚卸しする。

線の強弱は「線を2値化してから太らせる」。2値化は 0.15 を境に 0/1 へ
倒すので、線の**濃さ**を変える既存機能は、その前段にいると効果が
消える。実際、遠景つぶれ軽減は 0.9 まで上げても絵が1ビットも
変わらなかった。

同じ理由で消える恐れのあるものを、実機で1つずつ確かめる。
比べるのは「強弱OFFでの効き」と「強弱ONでの効き」。

  blender -b --factory-startup --python eval_lw_conflict.py -- \
      --out <dir> [--res 1600]
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
OUT = Path(arg("--out", str(HERE / "out" / "conflict"))).resolve()
RES_W = int(arg("--res", "1600"))
MODEL = arg("--model", "camera*")

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

# 確かめる項目。(名前, 既定に戻す値, 効かせる値) を並べる
CASES = [
    ("遠景つぶれ軽減", {"fp_far_relief": 0.0},
     {"fp_far_relief": 0.9, "fp_far_relief_radius": 5.0,
      "fp_far_relief_threshold": 0.2}),
    ("チャンネル別の強さ(メカ)", {"fp_ch_mecha": 1.0}, {"fp_ch_mecha": 0.3}),
    ("チャンネル別の強さ(深度)", {"fp_ch_depth": 1.0}, {"fp_ch_depth": 0.3}),
    ("アンチエイリアス", {"fp_include_antialiasing": True},
     {"fp_include_antialiasing": False}),
]


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


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
    a = math.radians(30.0)

    def place(d):
        cam.location = (center.x + math.sin(a) * d, center.y - math.cos(a) * d,
                        center.z + d * 0.22)
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


def setup(weight: bool):
    """モデルを読み、STEP0 まで通す。強弱の有無で島の切り方も変わる。"""
    blend = dm.find_blend(MODEL)
    if blend is None:
        raise SystemExit(f"見つからない: {MODEL}")
    meshes, _ = dm.load(blend)
    dm.grey(meshes)
    r = stage(meshes)
    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    sc.fp_auto_supersample = False
    sc.fp_line_weight = weight
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    sc.fp_supersample = False
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W * 2
    sc.render.resolution_y = RES_H * 2
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    if weight:
        bpy.ops.freepencil.measure_line_weight()
    return sc


def shot(sc, name):
    bpy.ops.freepencil2.link_button()      # STEP3 をやり直して反映
    sc.fp_white_preview = True
    fp_batch.render_still(sc, OUT / f"{name}.png", 2)


def main() -> None:
    fp_batch.install_addon()
    rows = []
    for weight in (False, True):
        tag = "on" if weight else "off"
        sc = setup(weight)
        for label, base, use in CASES:
            for k, v in base.items():
                setattr(sc, k, v)
            shot(sc, f"{tag}_{_slug(label)}_base")
            for k, v in use.items():
                setattr(sc, k, v)
            shot(sc, f"{tag}_{_slug(label)}_use")
            for k, v in base.items():
                setattr(sc, k, v)
            rows.append({"weight": tag, "case": label})
            say(f"強弱{tag} / {label}")
    (OUT / "conflict.json").write_text(json.dumps(
        {"model": MODEL, "res": [RES_W, RES_H], "rows": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


def _slug(label: str) -> str:
    return {"遠景つぶれ軽減": "relief", "チャンネル別の強さ(メカ)": "chmecha",
            "チャンネル別の強さ(深度)": "chdepth",
            "アンチエイリアス": "aa"}[label]


if __name__ == "__main__":
    main()
