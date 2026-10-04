"""人工分割の角度の下限を振って、最適値を探す。

「一様に滑らかで構造線が無い」枝に落ちたモデルは、p50×0.95 で分割線を
人工的に作る。下限が 5度 だと、なめらかに曲がる面のどこでも超えるので、
切れ目が形と関係ない場所に落ちる(サブサーフ適用済みのスザンヌで 6.2度、
耳の裏がメカのパネルのように割れた)。

下限を上げれば耳は直るが、上げすぎると「本当に構造線が無いモデル」で
内側の線が消える。その境目を実モデルで探す。

見るのは2つ。
    内側の線   輪郭から離れた線の画素。これが消えるとのっぺりする
    島の数     人工分割の量そのもの

  blender -b --factory-startup --python eval_split_floor.py -- \
      --out <dir> [--floors 5,10,14,18] [--limit 40]
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
OUT = Path(arg("--out", str(HERE / "out" / "split_floor"))).resolve()
RES = int(arg("--res", "900"))
LIMIT = int(arg("--limit", "40"))
FLOORS = [float(x) for x in arg("--floors", "5,10,14,18").split(",")]
ONLY = arg("--only")

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


def prep(sc):
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES * 2
    sc.render.resolution_y = RES * 2
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True


def inside_ink(path):
    """輪郭から離れた「内側の線」の量を測る。

    輪郭線はどの設定でも出るので、それを数えても差が見えない。
    シルエットを少し内側へ削ってから線を数える。
    """
    # Blender の Python に PIL は入っていない。bpy で読む
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
    # シルエットを 6px 削る。輪郭線と、その内側の縁取りを除く
    inner = alpha.copy()
    for _ in range(6):
        inner = (inner
                 & np.roll(inner, 1, 0) & np.roll(inner, -1, 0)
                 & np.roll(inner, 1, 1) & np.roll(inner, -1, 1))
    return int((ink & inner).sum()), int(alpha.sum())


def main() -> None:
    fp_batch.install_addon()
    models = scan_models.scan(scan_models.DEFAULT_ROOT)[:LIMIT]
    if ONLY:
        models = [m for m in models if ONLY in Path(m["path"]).stem]
    rows = []
    for m in models:
        name = Path(m["path"]).stem[:28]
        per = {}
        branch = None
        for floor in FLOORS:
            try:
                meshes, _ = dm.load(m["path"])
                dm.grey(meshes)
                stage(meshes)
            except Exception as e:                       # noqa: BLE001
                say(f"{name}: 読み込み失敗 {type(e).__name__}")
                per = {}
                break
            sc = bpy.context.scene
            prep(sc)
            sc.fp_auto_split_floor = floor
            bpy.ops.object.select_all(action="DESELECT")
            for o in meshes:
                o.select_set(True)
            bpy.context.view_layer.objects.active = meshes[0]
            bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
            sc.fp_white_preview = True
            png = OUT / f"{name}_f{int(floor):02d}.png"
            fp_batch.render_still(sc, png, 2)
            ink, sil = inside_ink(png)
            per[floor] = {"inside": ink, "sil": sil,
                          "ratio": round(ink / max(sil, 1) * 100, 4)}
        if not per:
            continue
        base = per[FLOORS[0]]["inside"]
        keep = {f: round(per[f]["inside"] / max(base, 1) * 100, 1)
                for f in FLOORS}
        rows.append({"model": name, "per": per, "keep": keep})
        say(f"{name:<30} 内側の線 " +
            "  ".join(f"{f:.0f}度:{keep[f]:5.1f}%" for f in FLOORS))
    (OUT / "floor.json").write_text(json.dumps(
        {"floors": FLOORS, "res": RES, "rows": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {len(rows)}体 {OUT}")


if __name__ == "__main__":
    main()
