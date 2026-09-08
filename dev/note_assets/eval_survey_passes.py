"""コンポジタに届く材料を全部並べて、何が作れるかを見極める。

v2.8 で足せる機能の当たりをつけるための下調べ。線の太さや抜きを
決めるには「線に沿って連続に変わるスカラー場」が要る。どの材料が
それになり得るかは、実際に出してみないと分からない。

出すもの: 使えるパスを全部レンダして1枚に並べる。あわせて、
線の画素の上でその値がどれだけ振れるか(=強弱に使えるか)を測る。

  blender -b --factory-startup --python eval_survey_passes.py -- \
      --out <dir> [--res 1920] [--model sphere|suzanne|<pattern>]
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
OUT = Path(arg("--out", str(HERE / "out" / "survey"))).resolve()
RES_W = int(arg("--res", "1920"))
MODEL = arg("--model", "suzanne")
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

# 有効化プロパティ -> 期待するソケット名の候補。バージョンで名前が
# 変わるので候補を並べて、実際に生えたものを拾う
PASSES = [
    ("use_pass_z", ("Depth",)),
    ("use_pass_mist", ("Mist",)),
    ("use_pass_normal", ("Normal",)),
    ("use_pass_position", ("Position",)),
    ("use_pass_vector", ("Vector",)),
    ("use_pass_object_index", ("IndexOB",)),
    ("use_pass_material_index", ("IndexMA",)),
    ("use_pass_diffuse_direct", ("Diffuse Direct", "DiffDir")),
    ("use_pass_diffuse_color", ("Diffuse Color", "DiffCol")),
    ("use_pass_glossy_direct", ("Glossy Direct", "GlossDir")),
    ("use_pass_shadow", ("Shadow",)),
    ("use_pass_ambient_occlusion", ("AO",)),
    ("use_pass_emit", ("Emit",)),
    ("use_pass_environment", ("Env",)),
    ("use_pass_transmission_direct", ("Transmission Direct", "TransDir")),
]


# 見る用の正規化。生の値域はパスごとに違う
PASS_RANGE = {
    "Normal": (-1.0, 1.0),
    "Position": (-3.0, 3.0),
    "Vector": (-4.0, 4.0),
    "Mist": (0.0, 0.05),
    "DiffDir": (0.0, 1.2),
    "DiffCol": (0.0, 1.0),
    "AO": (0.0, 1.0),
}


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    if MODEL == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=96,
                                             ring_count=48)
        o = bpy.context.object
        bpy.ops.object.shade_smooth()
        return [o]
    if MODEL == "suzanne":
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
    a = math.radians(VIEW_DEG)

    def place(d):
        cam.location = (center.x + math.sin(a) * d, center.y - math.cos(a) * d,
                        center.z + d * 0.14)
        cam.rotation_euler = (center - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    dist = r * 3.0
    from bpy_extras.object_utils import world_to_camera_view
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
    return dist


def enable_passes(vl):
    """立つものだけ立てる。無いプロパティは黙って飛ばす。"""
    on = []
    for prop, _ in PASSES:
        if hasattr(vl, prop):
            try:
                setattr(vl, prop, True)
                on.append(prop)
            except Exception:
                pass
        elif hasattr(vl.cycles if hasattr(vl, "cycles") else object, prop):
            pass
    return on


def main() -> None:
    fp_batch.install_addon()
    meshes = build()
    dm.grey(meshes)
    dist = stage(meshes)

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
    # 使える AOV は全部出す
    sc.fp_bone_color = True
    sc.fp_gen_color = True
    sc.fp_mask_color = True
    sc.fp_line_color = True
    sc.fp_mat_color = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True

    on = enable_passes(vl)
    say(f"立てたパス {len(on)}: {', '.join(p[9:] for p in on)}")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    # まず線を撮る
    sc.use_nodes = True
    fp_batch.render_still(sc, OUT / "line.png", 1)

    # 実際に生えたソケットを数える
    sc.use_nodes = True
    tree = sc.node_tree
    rl = next((n for n in tree.nodes if n.type == "R_LAYERS"), None)
    socks = [s.name for s in rl.outputs if s.enabled] if rl else []
    say(f"レイヤーノードのソケット {len(socks)}: {', '.join(socks)}")

    # 各ソケットを個別に書き出す。EXR は生の値、PNG は目で見る用。
    # PNG 側は正規化を挟む。法線は -1..1 なので 0..1 へ、深度は
    # 被写体の範囲へ合わせないと真っ白か真っ黒にしかならない
    (OUT / "pass").mkdir(parents=True, exist_ok=True)
    (OUT / "view").mkdir(parents=True, exist_ok=True)
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.base_path = str(OUT / "pass")
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.file_slots.clear()
    vo = tree.nodes.new("CompositorNodeOutputFile")
    vo.base_path = str(OUT / "view")
    vo.format.file_format = "PNG"
    vo.file_slots.clear()
    written = []
    for s in socks:
        if s in ("Image", "Alpha"):
            continue
        fo.file_slots.new(s.replace(" ", "_"))
        tree.links.new(rl.outputs[s], fo.inputs[-1])
        # 見る用。値域をだいたい 0..1 に寄せる
        mr = tree.nodes.new("CompositorNodeMapRange")
        lo, hi = PASS_RANGE.get(s, (0.0, 1.0))
        if s == "Depth":
            lo, hi = dist * 0.6, dist * 1.4
        mr.inputs[1].default_value = lo
        mr.inputs[2].default_value = hi
        mr.inputs[3].default_value = 0.0
        mr.inputs[4].default_value = 1.0
        tree.links.new(rl.outputs[s], mr.inputs[0])
        vo.file_slots.new(s.replace(" ", "_"))
        tree.links.new(mr.outputs[0], vo.inputs[-1])
        written.append(s)
    sc.frame_set(1)
    bpy.ops.render.render(write_still=False)
    say(f"書き出した {len(written)}")

    (OUT / "survey.json").write_text(json.dumps(
        {"model": MODEL, "res": [RES_W, RES_H], "engine": sc.render.engine,
         "blender": bpy.app.version_string, "sockets": socks,
         "written": written}, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
