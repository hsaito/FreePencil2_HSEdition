"""14度で潰れた卵を、既存のチャンネルで取り戻せるかを試す。

卵は1個1オブジェクトで、互いに接している。塗り分けで色が同じでも、
面までの距離は違うのだから、深度の線が境目を拾えるはず。拾えるなら
「人工分割の下限を上げる」ことの唯一の代償が消える。

深度の強さ(fp_ch_depth)は既定1.0、上限2.0。0/1/2 の3点で見る。
比較のため、いまの既定(5度/0.25)も撮る。

  blender -b --factory-startup --python eval_eggs_depth.py -- [--res 900]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "eggs_depth"))).resolve()
RES = int(arg("--res", "900"))
# depth = 深度チャンネル / mat = マテリアルチャンネル。
# AOV グループの中で Object Info の Random が mat_color を駆動している
# ことが分かったので、オブジェクトごとの差はもともと mat 側にある
CH = arg("--ch", "depth")

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)


def say(m):
    print(f"@@@ {m}", flush=True)


def stage(meshes):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
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
    d = r * 3.1
    cam.location = (ctr.x + math.sin(a) * d, ctr.y - math.cos(a) * d,
                    ctr.z + d * 0.30)
    cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat(
        "-Z", "Y").to_euler()
    cd.clip_end = d * 30
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(62), 0, math.radians(40) + a)


def run(path, floor, ridge, depth, tag):
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
    sc.fp_auto_split_floor = floor
    sc.fp_auto_merge = False
    sc.fp_min_island_area_pct = 1.0
    sc.fp_ridge_amount = ridge
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
    # STEP0 のあとに入れる。自動設定が線の強さも触るため
    if CH == "depth":
        sc.fp_ch_depth = depth
    else:
        sc.fp_ch_mat = depth
    sc.fp_white_preview = True
    fp_batch.render_still(sc, OUT / f"{tag}.png", 2)
    say(f"{tag} (下限{floor} 稜線{ridge} 深度{depth}) 完了")


def main():
    fp_batch.install_addon()
    path = next(m["path"] for m in scan_models.scan(scan_models.DEFAULT_ROOT)
                if "eggs_bowl" in Path(m["path"]).stem)
    run(path, 5.0, 0.25, 1.0, "a_now")
    run(path, 14.0, 0.45, 0.0, f"b_{CH}0")
    run(path, 14.0, 0.45, 1.0, f"c_{CH}1")
    run(path, 14.0, 0.45, 2.0, f"d_{CH}2")


if __name__ == "__main__":
    main()
