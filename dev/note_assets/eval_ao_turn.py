"""AO(くぼみ)で線に強弱を付けて、回しても崩れないかを見る。

光で抜く方式は、カメラを回すと抜き位置がモデル上を動くので、光を
カメラに追従させる必要があった。AO は形だけで決まるので、原理上は
回しても絵柄が動かないはずである。それを実際に確かめる。

1フレームにつき3枚撮る。線はアドオンの出力、AO と光はレンダーパスを
File Output でそのまま抜く。合成は eval_ao_mix.py が画像の上で行う。

AO と光は色管理を通さない(Standard)。通すと値が変わって、段を切る
分位点がフレームごとにずれる。

  blender -b --factory-startup --python eval_ao_turn.py -- \
      --out <dir> [--frames 72] [--res 1920] [--turn 360]
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
OUT = Path(arg("--out", str(HERE / "out" / "ao_turn"))).resolve()
RES_W = int(arg("--res", "1920"))
FRAMES = int(arg("--frames", "72"))
TURN = float(arg("--turn", "360"))
MODEL = arg("--model", "suzanne")
SUBDIV = int(arg("--subdiv", "2"))
LIGHT_AZ = float(arg("--light", "40"))
LIGHT_EL = float(arg("--elev", "62"))
AO_DIST = float(arg("--ao-dist", "0.6"))
# 土台の線は eval_base_line.py で決めた値
MERGE = float(arg("--merge", "0.3"))
RIDGE = float(arg("--ridge", "0.25"))
SENS = float(arg("--sens", "0.25"))

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
    if MODEL == "suzanne":
        bpy.ops.mesh.primitive_monkey_add()
        o = bpy.context.object
        if SUBDIV > 0:
            m = o.modifiers.new("Subdivision", "SUBSURF")
            m.levels = m.render_levels = SUBDIV
            bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.ops.object.shade_smooth()
        return [o]
    blend = dm.find_blend(MODEL)
    if blend is None:
        raise SystemExit(f"見つからない: {MODEL}")
    meshes, _ = dm.load(blend)
    return meshes


def stage(meshes):
    """カメラは周回。回しても切れないよう、全周ぶんの外接で合わせる。"""
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
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

    # 全周のどの角度でも収まる距離を採る。1角度だけで合わせると、
    # 横を向いたとき鼻先が画面から出る
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
        dist *= m * 1.06
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
    return cam, key, center, dist, place


def add_pass_output(sc):
    """AO と光を、色管理を通さずそのまま書き出すノードを足す。

    アドオンが組んだツリーに足すだけなので、1回のレンダで線と一緒に出る。
    ツリーを作り直してはいけない。一度 nodes.clear() で組み直す実装に
    したところ、3Dのレンダごと飛んで合成だけが走り、出力が空になった。
    """
    tree = sc.node_tree
    rl = next((n for n in tree.nodes if n.type == "R_LAYERS"), None)
    if rl is None:
        raise SystemExit("レンダーレイヤーノードが無い")
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.base_path = str(OUT)
    fo.format.file_format = "PNG"
    fo.format.color_mode = "BW"
    fo.format.color_depth = "16"
    # 色管理を通すと値が変わり、段を切る分位点がフレームごとにずれる
    fo.format.color_management = "OVERRIDE"
    fo.format.view_settings.view_transform = "Standard"
    fo.format.view_settings.look = "None"
    fo.file_slots.clear()
    for sock, sub in (("AO", "ao"), ("DiffDir", "light")):
        if sock not in rl.outputs or not rl.outputs[sock].enabled:
            say(f"  ソケットが無い: {sock}")
            continue
        fo.file_slots.new(f"{sub}/f")
        tree.links.new(rl.outputs[sock], fo.inputs[-1])
    return fo


def main() -> None:
    fp_batch.install_addon()
    meshes = build()
    dm.grey(meshes)
    cam, key, center, dist, place = stage(meshes)

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
    sc.fp_auto_merge = False
    sc.fp_auto_sharp = False
    sc.fp_sharp_auto = True
    sc.fp_min_island_area_pct = MERGE
    sc.fp_ridge_amount = RIDGE
    sc.fp_ridge_radius = 0.08
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    sc.fp_line_sensitivity = SENS
    say(f"STEP0 {time.time() - t:.1f}秒 / メッシュ {len(meshes)}")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    vl.use_pass_ambient_occlusion = True
    vl.use_pass_diffuse_direct = True
    # AO の半径。4.5 は gtao_distance を持つ。5.x では fast_gi 系だけ
    if hasattr(sc.eevee, "use_gtao"):
        sc.eevee.use_gtao = True
    if hasattr(sc.eevee, "gtao_distance"):
        sc.eevee.gtao_distance = AO_DIST
    if hasattr(sc.eevee, "fast_gi_distance"):
        sc.eevee.fast_gi_distance = AO_DIST

    sc.use_nodes = True
    add_pass_output(sc)
    (OUT / "line").mkdir(parents=True, exist_ok=True)

    t = time.time()
    for f in range(FRAMES):
        a = math.radians(TURN * f / FRAMES)
        place(dist, a)
        # 光はカメラ追従。世界固定は回転で破綻することが分かっている
        key.rotation_euler = (math.radians(LIGHT_EL), 0.0,
                              math.radians(LIGHT_AZ) + a)
        bpy.context.view_layer.update()
        sc.frame_set(f + 1)
        fp_batch.render_still(sc, OUT / "line" / f"f{f:04d}.png", 1)
        if (f + 1) % 12 == 0:
            say(f"  {f + 1}/{FRAMES} ({time.time() - t:.0f}s)")

    (OUT / "turn.json").write_text(json.dumps(
        {"frames": FRAMES, "turn": TURN, "res": [RES_W, RES_H],
         "light": [LIGHT_AZ, LIGHT_EL], "ao_dist": AO_DIST, "model": MODEL,
         "merge": MERGE, "ridge": RIDGE, "sens": SENS},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
