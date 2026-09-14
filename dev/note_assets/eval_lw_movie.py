"""デモ動画の素材を撮る。アドオンの「線の強弱(くぼみ)」を実機で回す。

Python で合成した絵ではなく、アドオンが組んだノードが出した絵を撮る。
使う人と同じ手順で回す。

    STEP0 -> しきい値を1回測る -> 強弱OFF で1周 -> 強弱ON で1周

しきい値はカットの頭で1回だけ測って固定する。フレームごとに測り直す
と絵が変わるたびにしきい値が動いて線がちらつく(実測26%)。

  blender -b --factory-startup --python eval_lw_movie.py -- \
      --out <dir> [--frames 120] [--res 1920]
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
OUT = Path(arg("--out", str(HERE / "out" / "lw_movie"))).resolve()
RES_W = int(arg("--res", "1920"))
FRAMES = int(arg("--frames", "120"))
TURN = float(arg("--turn", "360"))
MODEL = arg("--model", "suzanne")

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
    if MODEL == "suzanne":
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_monkey_add()
        o = bpy.context.object
        m = o.modifiers.new("Subdivision", "SUBSURF")
        m.levels = m.render_levels = 2
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.ops.object.shade_smooth()
        return [o]
    blend = dm.find_blend(MODEL)
    if blend is None:
        raise SystemExit(f"見つからない: {MODEL}")
    meshes, _ = dm.load(blend)
    return meshes


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

    def place(d, ang):
        cam.location = (center.x + math.sin(ang) * d,
                        center.y - math.cos(ang) * d,
                        center.z + d * 0.14)
        cam.rotation_euler = (center - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    # 全周のどの角度でも収まる距離。1角度で合わせると横で鼻先が出る
    from bpy_extras.object_utils import world_to_camera_view
    dist = r * 3.0
    probe = [math.radians(t) for t in range(0, 360, 30)]
    for _ in range(3):
        m = 0.0
        for ang in probe:
            place(dist, ang)
            for p in pts:
                q = world_to_camera_view(sc, cam, p)
                m = max(m, abs(q.x - 0.5) * 2.0, abs(q.y - 0.5) * 2.0)
        dist *= m * 1.04
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
    key.rotation_euler = (math.radians(62), 0.0, math.radians(40))
    return r, dist, place


def shoot(sc, place, dist, sub):
    (OUT / sub).mkdir(parents=True, exist_ok=True)
    t = time.time()
    for f in range(FRAMES):
        place(dist, math.radians(TURN * f / FRAMES))
        sc.frame_set(f + 1)
        fp_batch.render_still(sc, OUT / sub / f"f{f:04d}.png", 1)
        if (f + 1) % 30 == 0:
            say(f"  {sub} {f + 1}/{FRAMES} ({time.time() - t:.0f}s)")


def main() -> None:
    fp_batch.install_addon()
    meshes = build()
    dm.grey(meshes)
    r, dist, place = stage(meshes)

    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    # 出荷どおり細線化 ON (pct=200) でアドオンに縮小させる。以前は
    # pct=100 で解像度を2倍にして保存時に縮めていたが、アドオンは倍率を
    # 見て太さとぼかしを pct/200 で割るので、その経路では強弱が本来の
    # 半分で写っていた(実測)。F12 の額縁の件は render_size で直っている
    sc.fp_auto_supersample = True
    # 以前はスザンヌ用に島0.3・稜線0.25・感度0.25 を手で入れていた
    # (v2.6.2 の土台で撮ったときの調整)。既定を 14度 + 稜線0.45 に
    # 変えたので、何も上書きせず STEP0 に任せる。使う人と同じ絵になる
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True

    assert sc.render.resolution_percentage == 200, "細線化が倍率に効いていない"
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    place(dist, 0.0)
    shoot(sc, place, dist, "off")

    sc.fp_line_weight = True
    # 島を切る細かさは STEP1 で決まる。強弱をONにしてから STEP0 を
    # やり直さないと反映されない
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    place(dist, 0.0)
    bpy.ops.freepencil.measure_line_weight()
    edges = [round(getattr(sc, f"fp_lw_e{i}"), 5) for i in range(1, 5)]
    say(f"しきい値(カット内で固定) {edges}")
    bpy.ops.freepencil2.link_button()      # STEP3 をやり直す
    sc.fp_white_preview = True
    shoot(sc, place, dist, "on")

    (OUT / "movie.json").write_text(json.dumps(
        {"frames": FRAMES, "turn": TURN, "res": [RES_W, RES_H],
         "model": MODEL, "edges": edges, "ao_dist": round(sc.fp_lw_ao_dist, 4)},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
