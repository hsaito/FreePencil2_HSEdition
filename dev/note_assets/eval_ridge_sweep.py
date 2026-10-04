"""稜線の起伏をふって、0.45 が最適なのか、上限に寄せすぎていないかを見る。

0.25 と 0.45 の2点しか測っていないので「0.45 が良い」は言えても
「0.45 が最適」は言えない。props.py の上限は 0.5 で、コメントには
「隣接島の色距離の契約(既定0.5)を割らないよう小さく保つ」とある。
0.45 は上限のすぐ下なので、そこが安全圏なのかを確かめる必要がある。

測るもの:
    内側の線   0.25 を 100% としたときの量
    最大ズレ   稜線が色をどれだけ動かしたか(本体のログから拾う)

  blender -b --factory-startup --python eval_ridge_sweep.py -- \
      --out <dir> [--ridges 0.25,0.35,0.45,0.50] [--res 800]
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
OUT = Path(arg("--out", str(HERE / "out" / "ridge_sweep"))).resolve()
RES = int(arg("--res", "800"))
RIDGES = [float(x) for x in arg("--ridges", "0.25,0.35,0.45,0.50").split(",")]
# 稜線が効いた体と、効かないはずのメカ・平面を混ぜる
WANT = arg("--only", "baccarat,cupcakes,arched_hangar,bed_2K,camera_2K,"
                     "kaino-school,anime-girl,cat_figurine,lancia,clay-vase")

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
SHIFT = []


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def patch_shift():
    """本体が計算した色のズレ量を、絵とは別に拾っておく。"""
    from freepencil2 import mesh_islands
    real = mesh_islands.ridge_residual

    def probe(mesh, radius_frac):
        got = real(mesh, radius_frac)
        if got is not None:
            # 本体は d * ridge_amount を色へ足す。残差そのものではなく、
            # 実際に色が動く量を記録しないと意味が無い
            amt = float(getattr(bpy.context.scene, "fp_ridge_amount", 0.0))
            SHIFT.append(float(np.abs(got[0]).max()) * amt)
        return got

    mesh_islands.ridge_residual = probe
    import freepencil2.vertex_color as vc
    vc.mesh_islands.ridge_residual = probe


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
                        ctr.z + d * 0.22)
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


def run(path, ridge, png):
    SHIFT.clear()
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
    sc.fp_white_preview = True
    fp_batch.render_still(sc, png, 2)
    return measure(png), (max(SHIFT) if SHIFT else 0.0)


def main():
    fp_batch.install_addon()
    patch_shift()
    pats = [x for x in WANT.split(",") if x]
    models = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
              if any(p in Path(m["path"]).stem for p in pats)]
    rows = []
    for m in models:
        name = Path(m["path"]).stem[:28]
        per = {}
        try:
            for r in RIDGES:
                png = OUT / f"{name}_r{int(r * 100):03d}.png"
                per[r] = run(m["path"], r, png)
        except Exception as e:                     # noqa: BLE001
            say(f"{name}: 失敗 {type(e).__name__}: {e}")
            continue
        base = per[RIDGES[0]][0]
        rows.append({"model": name,
                     "keep": {str(r): round(per[r][0] / max(base, 1) * 100, 1)
                              for r in RIDGES},
                     "shift": {str(r): round(per[r][1], 4) for r in RIDGES}})
        say(f"{name:<30} " + "  ".join(
            f"{r:.2f}:{per[r][0] / max(base, 1) * 100:6.1f}%"
            f"(ズレ{per[r][1]:.3f})" for r in RIDGES))
    (OUT / "ridge.json").write_text(json.dumps(
        {"ridges": RIDGES, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    if rows:
        say("")
        for r in RIDGES:
            v = np.array([x["keep"][str(r)] for x in rows])
            s = np.array([x["shift"][str(r)] for x in rows])
            say(f"稜線 {r:.2f}  内側の線 中央 {np.median(v):6.1f}%  "
                f"最小 {v.min():6.1f}%  色のズレ 最大 {s.max():.3f}")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
