"""AO の値が、モデルが変わってもだいたい同じ範囲に収まるかを調べる。

段を切るしきい値をどう決めるかが問題になっている。分位点で切ると
絵ごと・フレームごとに動いてちらつく。かといって絶対値で切ると、
モデルによっては全部が同じ段に入って強弱が消える(遠景つぶれ軽減で
一度やった失敗)。

AO は 0..1 の物理量なので、絶対値で切れる見込みがある。それを
実モデルで確かめる。見るのは「線の画素における d = 1 - AO」の分位点。
モデル間でばらつかなければ、既定値を1組決めて配れる。

  blender -b --factory-startup --python eval_ao_models.py -- \
      --out <dir> [--n 8] [--res 1600]
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
OUT = Path(arg("--out", str(HERE / "out" / "ao_models"))).resolve()
RES_W = int(arg("--res", "1600"))
LIMIT = int(arg("--n", "8"))
AO_DIST = float(arg("--ao-dist", "0.6"))

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

# 種類が偏らないように選ぶ。人・メカ・乗り物・小物・建物
WANT = ["anime-girl*", "audi_r8*", "batmobile*", "cat_figurine*",
        "clay-vase*", "camera*", "chair*", "arched_hangar*",
        "cleaver_knife*", "43-inch-tv*", "baseball_01*", "bed_f5*"]


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
    # モデルの大きさはまちまちなので、AO の半径も大きさに合わせる。
    # 固定にすると、大きい建物では何も遮蔽されず AO が真っ白になる
    return r


def one(pattern: str):
    blend = dm.find_blend(pattern)
    if blend is None:
        return None
    meshes, _ = dm.load(blend)
    dm.grey(meshes)
    r = stage(meshes)

    sc = bpy.context.scene
    vl = bpy.context.view_layer
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
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    sc.fp_line_sensitivity = 0.5

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    vl.use_pass_ambient_occlusion = True
    if hasattr(sc.eevee, "use_gtao"):
        sc.eevee.use_gtao = True
    # 半径はモデルの大きさに比例させる
    d = r * AO_DIST
    if hasattr(sc.eevee, "gtao_distance"):
        sc.eevee.gtao_distance = d
    if hasattr(sc.eevee, "fast_gi_distance"):
        sc.eevee.fast_gi_distance = d

    name = pattern.rstrip("*")
    sc.use_nodes = True
    tree = sc.node_tree
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.base_path = str(OUT)
    fo.format.file_format = "PNG"
    fo.format.color_mode = "BW"
    fo.format.color_depth = "16"
    fo.format.color_management = "OVERRIDE"
    fo.format.view_settings.view_transform = "Standard"
    fo.format.view_settings.look = "None"
    fo.file_slots.clear()
    fo.file_slots.new(f"ao/{name}")
    tree.links.new(rl.outputs["AO"], fo.inputs[-1])
    sc.frame_set(1)
    fp_batch.render_still(sc, OUT / "line" / f"{name}.png", 1)
    return {"model": name, "meshes": len(meshes), "radius": round(r, 3),
            "ao_dist": round(d, 3)}


def main() -> None:
    fp_batch.install_addon()
    (OUT / "line").mkdir(parents=True, exist_ok=True)
    rows = []
    for pat in WANT[:LIMIT]:
        try:
            r = one(pat)
        except Exception as e:                       # noqa: BLE001
            say(f"{pat}: 失敗 {e}")
            continue
        if r is None:
            say(f"{pat}: 見つからない")
            continue
        rows.append(r)
        say(f"{r['model']}  メッシュ{r['meshes']}  半径{r['radius']}"
            f"  AO半径{r['ao_dist']}")
    (OUT / "models.json").write_text(json.dumps(
        {"res": [RES_W, RES_H], "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {len(rows)}体 {OUT}")


if __name__ == "__main__":
    main()
