"""深度チャンネルの強さをふる。卵の件から出てきた案。

eggs_bowl は「人工分割が卵に偽の輪を描いていた」だけで、14度に上げても
卵の輪郭は深度の線が保っていた。しかも深度を 2.0 にすると、いまの
既定よりはっきり分かれた。つまり深度は効く場面では効くのに、既定の
1.0 は控えめすぎる可能性がある。

深度が効くのは「別々のものが重なっている」場面だけなので、そういう
モデルを選んで振る。効かないモデルでは何も変わらないはずで、そこが
確かめたい点でもある(上げても汚れないか)。

  blender -b --factory-startup --python eval_depth_sweep.py -- \
      --out <dir> [--depths 0.5,1.0,1.5,2.0] [--res 800]
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
OUT = Path(arg("--out", str(HERE / "out" / "depth_sweep"))).resolve()
RES = int(arg("--res", "800"))
DEPTHS = [float(x) for x in arg("--depths", "0.5,1.0,1.5,2.0").split(",")]
# 重なりのあるもの(卵/カップケーキ/本/骨格/船/団地)と、
# 重なりの無い単体もの(壺/カメラ/猫)を混ぜる
WANT = arg("--only", "eggs_bowl,cupcakes,books-pack,full-skeleton,"
                     "dutch_ship,japan-apartment,clay-vase,camera_2K,"
                     "cat_figurine,kaino-school")
# 下限と稜線は提案値で固定する。深度だけを見たい
FLOOR = float(arg("--floor", "14.0"))
RIDGE = float(arg("--ridge", "0.45"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def stage(meshes):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes
           for c in o.bound_box if not o.hide_render]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    ctr = Vector(((min(xs) + max(xs)) * .5, (min(ys) + max(ys)) * .5,
                  (min(zs) + max(zs)) * .5))
    r = max((p - ctr).length for p in pts)
    cd = bpy.data.cameras.new("C")
    cd.lens = 55.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(30.0)
    from bpy_extras.object_utils import world_to_camera_view

    def place(d):
        cam.location = (ctr.x + math.sin(a) * d, ctr.y - math.cos(a) * d,
                        ctr.z + d * 0.26)
        cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    dist = r * 3.0
    for _ in range(3):
        place(dist)
        mm = max(max(abs(world_to_camera_view(sc, cam, p).x - .5) * 2,
                     abs(world_to_camera_view(sc, cam, p).y - .5) * 2)
                 for p in pts)
        dist *= mm * 1.10
    place(dist)
    cd.clip_end = dist * 30
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (.5, .5, .52, 1)
        bg.inputs[1].default_value = .15
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = 0.0
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(62), 0, math.radians(40) + a)


def measure(path):
    img = bpy.data.images.load(str(path))
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        a = buf.reshape(h, w, 4).astype(np.float64)
    finally:
        bpy.data.images.remove(img)
    alpha = a[..., 3] > .5
    ink = ((1.0 - a[..., :3].mean(axis=2)) > .5) & alpha
    inner = alpha.copy()
    for _ in range(6):
        inner = (inner & np.roll(inner, 1, 0) & np.roll(inner, -1, 0)
                 & np.roll(inner, 1, 1) & np.roll(inner, -1, 1))
    return int((ink & inner).sum())


def run(path, depth, png):
    meshes, _ = dm.load(path)
    dm.grey(meshes)
    stage(meshes)
    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_split_floor = FLOOR
    sc.fp_auto_merge = False
    sc.fp_min_island_area_pct = 1.0
    sc.fp_ridge_amount = RIDGE
    sc.fp_ridge_radius = 0.08
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES * 2
    sc.render.resolution_y = RES * 2
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    # STEP0 は線の強さも触るので、その後に入れる
    sc.fp_ch_depth = depth
    sc.fp_white_preview = True
    fp_batch.render_still(sc, png, 2)
    return measure(png)


def main():
    fp_batch.install_addon()
    pats = [x for x in WANT.split(",") if x]
    models = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
              if any(p in Path(m["path"]).stem for p in pats)]
    rows = []
    for m in models:
        name = Path(m["path"]).stem[:28]
        per = {}
        try:
            for dv in DEPTHS:
                per[dv] = run(m["path"], dv,
                              OUT / f"{name}_d{int(dv * 100):03d}.png")
        except Exception as e:                     # noqa: BLE001
            say(f"{name}: 失敗 {type(e).__name__}: {e}")
            continue
        base = per[1.0] if 1.0 in per else per[DEPTHS[0]]
        rows.append({"model": name,
                     "keep": {str(d): round(per[d] / max(base, 1) * 100, 1)
                              for d in DEPTHS}})
        say(f"{name:<30} " + "  ".join(
            f"{d:.1f}:{per[d] / max(base, 1) * 100:6.1f}%" for d in DEPTHS))
    (OUT / "depth.json").write_text(json.dumps(
        {"depths": DEPTHS, "floor": FLOOR, "ridge": RIDGE, "rows": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    if rows:
        say("")
        for d in DEPTHS:
            v = np.array([x["keep"][str(d)] for x in rows])
            say(f"深度 {d:.1f}  内側の線 中央 {np.median(v):6.1f}%  "
                f"最小 {v.min():6.1f}%  最大 {v.max():6.1f}%")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
