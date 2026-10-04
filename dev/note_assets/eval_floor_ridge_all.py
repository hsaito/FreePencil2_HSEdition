"""「14度 + 稜線0.45」を実アセットで徹底的に確かめる。

スザンヌ1体では通った(耳の横断線が消え、口が戻る)。ただし
    人工分割の下限   5度  -> 14度
    稜線の起伏      0.25 -> 0.45
はどちらも既定の変更で、STEP0 を通る全モデルに効く。メカのパネルが
稜線で汚れないか、内側の線が減らないかを、BlenderKit の実アセットで
1体ずつ見る。

出すもの:
    <name>_now.png   いまの既定(5度 / 0.25)
    <name>_new.png   提案(14度 / 0.45)
    all.json         1体ごとの数値

見る数値:
    内側の線   輪郭から6px内側の線の画素。形の情報そのもの
    インク     線の総量。増えすぎると絵が重い
    枝         choose_auto_threshold のどの枝に落ちたか(下限が効くのは
               「人工分割」の枝だけ)

  blender -b --factory-startup --python eval_floor_ridge_all.py -- \
      --out <dir> [--limit 60] [--res 900]
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
OUT = Path(arg("--out", str(HERE / "out" / "floor_all"))).resolve()
RES = int(arg("--res", "900"))
LIMIT = int(arg("--limit", "60"))

# (名前, 人工分割の下限, 稜線の起伏)
CONFIGS = [("now", 5.0, 0.25), ("new", 14.0, 0.45)]
if arg("--split-vars"):
    # 2つの変更のどちらが効いているかを切り分ける
    CONFIGS = [("now", 5.0, 0.25), ("f14", 14.0, 0.25),
               ("r45", 5.0, 0.45), ("new", 14.0, 0.45)]
ONLY = arg("--only", "")

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


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def stage(meshes):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes
           for c in o.bound_box if not o.hide_render]
    if not pts:
        raise RuntimeError("可視メッシュ無し")
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


def measure(path):
    """内側の線とインクを測る。輪郭線はどの設定でも出るので内側を見る。"""
    img = bpy.data.images.load(str(path))
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        a = buf.reshape(h, w, 4).astype(np.float64)
    finally:
        bpy.data.images.remove(img)
    alpha = a[..., 3] > 0.5
    ink = ((1.0 - a[..., :3].mean(axis=2)) > 0.5) & alpha
    inner = alpha.copy()
    for _ in range(6):
        inner = (inner
                 & np.roll(inner, 1, 0) & np.roll(inner, -1, 0)
                 & np.roll(inner, 1, 1) & np.roll(inner, -1, 1))
    return {"inside": int((ink & inner).sum()),
            "ink": int(ink.sum()),
            "sil": int(alpha.sum())}


def run_one(path, floor, ridge, png):
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
    # 稜線は STEP0 のおすすめ設定が 0.25 を上書きするので、そこを切って入れる
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
    return measure(png)


def main() -> None:
    fp_batch.install_addon()
    models = scan_models.scan(scan_models.DEFAULT_ROOT)[:LIMIT]
    if ONLY:
        pats = [x for x in ONLY.split(",") if x]
        models = [m for m in models
                  if any(p in Path(m["path"]).stem for p in pats)]
    rows = []
    for m in models:
        name = Path(m["path"]).stem[:28]
        per = {}
        ok = True
        for tag, floor, ridge in CONFIGS:
            try:
                per[tag] = run_one(m["path"], floor, ridge,
                                   OUT / f"{name}_{tag}.png")
            except Exception as e:                       # noqa: BLE001
                say(f"{name}: {tag} 失敗 {type(e).__name__}")
                ok = False
                break
        if not ok:
            continue
        a, b = per["now"], per[CONFIGS[-1][0]]
        d_in = (b["inside"] - a["inside"]) / max(a["inside"], 1) * 100
        d_ink = (b["ink"] - a["ink"]) / max(a["ink"], 1) * 100
        rows.append({"model": name, "now": a, "new": b,
                     "d_inside": round(d_in, 1), "d_ink": round(d_ink, 1)})
        flag = ""
        if d_in < -25:
            flag = "  ★内側が減った"
        elif d_in > 40:
            flag = "  ★内側が増えた"
        say(f"{name:<30} 内側 {d_in:+7.1f}%  インク {d_ink:+7.1f}%{flag}")
    (OUT / "all.json").write_text(json.dumps(
        {"configs": CONFIGS, "res": RES, "rows": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    if rows:
        di = np.array([r["d_inside"] for r in rows])
        say("")
        say(f"{len(rows)}体  内側の線の変化  中央 {np.median(di):+.1f}%  "
            f"最小 {di.min():+.1f}%  最大 {di.max():+.1f}%")
        say(f"  25%以上減った {int((di < -25).sum())}体  "
            f"40%以上増えた {int((di > 40).sum())}体")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
