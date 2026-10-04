"""スザンヌの素の線を最適化する。強弱を付ける前の土台づくり。

強弱(光による抜き)は土台の線を加工するだけなので、土台が悪ければ
何をしても良くならない。先にここを決める。

最初、線の感度とエッジ角度を振ったが、角度は効果ゼロだった
(3条件でインク率が完全に一致 0.426%)。稜線量も同じくゼロ。
理由は auto_setup.py:83-96 で、STEP0 の「おすすめ設定」が
fp_sharp_auto / fp_min_island_area_pct / fp_ridge_amount を
上書きしていたため。振るには fp_auto_sharp と fp_auto_merge を
切って自分で入れる必要がある。

そこで振るのはこの2つにした。どちらもSTEP0の焼きに効く。
    まとめ率   小さい島を吸収する面積%。0=細かい島が全部残る
    稜線量     なめらかな面の中へ、眉や折れの線を足す量

  blender -b --factory-startup --python eval_base_line.py -- \
      --out <dir> [--res 3840]
"""
from __future__ import annotations

import itertools
import json
import math
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "baseline"))).resolve()
RES_W = int(arg("--res", "3840"))
SUBDIV = int(arg("--subdiv", "2"))
VIEW_DEG = float(arg("--view", "20"))

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

# 一段目の結果で軸を絞った。まとめ率は 0.3 が最良(1.0 だと目の
# 虹彩の輪が消える。0.0 だとメッシュの格子が眉にハッチングとして出る)。
# 稜線は 0.25。残った欠点は「薄い線が2値化で途切れる」ことなので、
# 二段目は感度だけを振る
SENS = [float(arg("--sens", "0.25"))]
MERGE = [float(x) for x in arg("--merge", "0.3").split(",")]
RIDGE = [float(arg("--ridge", "0.25"))]
RIDGE_RADIUS = 0.08
BLUR = [int(x) for x in arg("--blur", "0").split(",")]


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
    # 距離は式で当てずに、実際に投影して合わせる。水平半径と高さで
    # 別々に見ると斜めから見たとき鼻先が下にはみ出して口が切れ、
    # 外接球で見ると今度は奥行きの分まで数えて顔が豆粒になった
    r = max((p - center).length for p in pts)
    lens = 55.0
    dist = r * 3.0
    cd = bpy.data.cameras.new("C")
    cd.lens = lens
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(VIEW_DEG)

    def place(d):
        cam.location = (center.x + math.sin(a) * d, center.y - math.cos(a) * d,
                        center.z + d * 0.14)
        look = center - Vector(cam.location)
        cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    # 実際に投影して、はみ出し量だけ引く。2回で十分収束する
    from bpy_extras.object_utils import world_to_camera_view
    for _ in range(3):
        place(dist)
        m = 0.0
        for p in pts:
            q = world_to_camera_view(sc, cam, p)
            m = max(m, abs(q.x - 0.5) * 2.0, abs(q.y - 0.5) * 2.0)
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
    return cam


def main() -> None:
    fp_batch.install_addon()
    rows = []
    for merge, ridge, sens, blur in itertools.product(
            MERGE, RIDGE, SENS, BLUR):
        meshes = build()
        dm.grey(meshes)
        stage(meshes)
        sc = bpy.context.scene
        sc.fp_use_random_seed = False
        sc.fp_color_seed = 42
        sc.fp_enable_compositor_view = False
        sc.fp_auto_detect_aov = False
        sc.fp_auto_supersample = False
        sc.fp_supersample = False
        sc.fp_auto_white_preview = False
        sc.fp_white_preview = True
        # STEP0 のおすすめ設定に上書きさせない
        sc.fp_auto_merge = False
        sc.fp_auto_sharp = False
        sc.fp_sharp_auto = True
        sc.fp_min_island_area_pct = merge
        sc.fp_ridge_amount = ridge
        sc.fp_ridge_radius = RIDGE_RADIUS
        sc.fp_curve_blur = blur
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sc.fp_white_preview = True
        sc.fp_line_sensitivity = sens

        sc.render.engine = fp_batch.eevee_engine()
        sc.eevee.taa_render_samples = 32
        sc.render.resolution_percentage = 100
        sc.render.resolution_x = RES_W
        sc.render.resolution_y = RES_H
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGBA"
        sc.render.film_transparent = True
        sc.use_nodes = True
        tag = f"m{int(merge * 100):03d}_b{blur:02d}"
        fp_batch.render_still(sc, OUT / f"{tag}.png", 1)
        # 陰影は最後の1回だけでよい(条件で変わらない)
        if not (OUT / "shade.png").exists():
            sc.use_nodes = False
            sc.fp_white_preview = False
            fp_batch.render_still(sc, OUT / "shade.png", 1)
        rows.append({"tag": tag, "sens": sens, "merge": merge,
                     "ridge": ridge, "blur": blur})
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{tag}.blend"))
        say(f"{tag}")

    (OUT / "base.json").write_text(json.dumps(
        {"res": [RES_W, RES_H], "view": VIEW_DEG, "rows": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
