"""AO の強弱をコンポジタのノードで組んで、Python版と一致するか見る。

Python(eval_best_line.py)で効くと分かった手順を、そのままノードに
置き換える。ここで一致しなければアドオンに入れる意味がない。

置き換え表:
    binarize        Math GREATER_THAN
    1 - AO          Math SUBTRACT
    段の切り出し     Math GREATER_THAN * LESS_THAN
    morph(px)       DilateErode (mode=STEP, distance=px)
    maximum         Math MAXIMUM
    50%縮小          既存のスーパーサンプリング(200%レンダ+Scale 0.5)
    gain            Math MULTIPLY

しきい値はモデルごとに大きく違う(実測: 11体で 20%点が 0.0013〜0.0193、
15倍の開き)ので、固定値では配れない。ここでは外から渡す。

  blender -b --factory-startup --python eval_ao_nodes.py -- \
      --out <dir> [--edges 0.0019,0.0147,0.0453,0.1051]
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
OUT = Path(arg("--out", str(HERE / "out" / "ao_nodes"))).resolve()
RES_W = int(arg("--res", "1920"))
VIEW_DEG = float(arg("--view", "20"))
AO_DIST = float(arg("--ao-dist", "0.6"))
BIN = float(arg("--bin", "0.15"))
GAIN = float(arg("--gain", "1.4"))
# 暗い(くぼんだ)側から太い順
LEVELS = [int(x) for x in arg("--levels", "5,4,3,2,1").split(",")]
EDGES = [float(x) for x in
         arg("--edges", "0.0019,0.0147,0.0453,0.1051").split(",")]

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
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("Subdivision", "SUBSURF")
    m.levels = m.render_levels = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    return [o]


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
    return r


def math_node(tree, op, x=0, y=0, a=None, b=None):
    n = tree.nodes.new("CompositorNodeMath")
    n.operation = op
    n.location = (x, y)
    if a is not None:
        n.inputs[0].default_value = a
    if b is not None:
        n.inputs[1].default_value = b
    return n


def build_weight(tree, line_sock, ao_sock, x0=600, y0=-200):
    """線に強弱を付ける枝を組む。入り口は線とAO、出口は線の色。"""
    inv = tree.nodes.new("CompositorNodeInvert")
    inv.location = (x0, y0)
    tree.links.new(line_sock, inv.inputs["Color"])

    # 2値化。薄い線を拾いたいのでしきい値は低め
    binz = math_node(tree, "GREATER_THAN", x0 + 200, y0, b=BIN)
    tree.links.new(inv.outputs[0], binz.inputs[0])

    # d = 1 - AO。くぼんでいるほど大きい
    dep = math_node(tree, "SUBTRACT", x0 + 200, y0 - 180, a=1.0)
    tree.links.new(ao_sock, dep.inputs[1])

    n = len(LEVELS)
    prev = None
    for k, px in enumerate(LEVELS):
        yy = y0 - 360 - k * 220
        band = None
        if k > 0:
            ge = math_node(tree, "GREATER_THAN", x0 + 400, yy, b=EDGES[k - 1])
            tree.links.new(dep.outputs[0], ge.inputs[0])
            band = ge
        if k < n - 1:
            lt = math_node(tree, "LESS_THAN", x0 + 400, yy - 90, b=EDGES[k])
            tree.links.new(dep.outputs[0], lt.inputs[0])
            if band is None:
                band = lt
            else:
                mul = math_node(tree, "MULTIPLY", x0 + 580, yy)
                tree.links.new(band.outputs[0], mul.inputs[0])
                tree.links.new(lt.outputs[0], mul.inputs[1])
                band = mul
        seg = math_node(tree, "MULTIPLY", x0 + 760, yy)
        tree.links.new(binz.outputs[0], seg.inputs[0])
        if band is None:
            seg.inputs[1].default_value = 1.0
        else:
            tree.links.new(band.outputs[0], seg.inputs[1])
        de = tree.nodes.new("CompositorNodeDilateErode")
        de.location = (x0 + 940, yy)
        de.mode = "STEP"
        de.distance = px
        tree.links.new(seg.outputs[0], de.inputs[0])
        if prev is None:
            prev = de
        else:
            mx_ = math_node(tree, "MAXIMUM", x0 + 1120, yy)
            tree.links.new(prev.outputs[0], mx_.inputs[0])
            tree.links.new(de.outputs[0], mx_.inputs[1])
            prev = mx_

    gain = math_node(tree, "MULTIPLY", x0 + 1320, y0 - 400, b=GAIN)
    tree.links.new(prev.outputs[0], gain.inputs[0])
    cl = math_node(tree, "MINIMUM", x0 + 1480, y0 - 400, b=1.0)
    tree.links.new(gain.outputs[0], cl.inputs[0])
    out = tree.nodes.new("CompositorNodeInvert")
    out.location = (x0 + 1660, y0 - 400)
    tree.links.new(cl.outputs[0], out.inputs["Color"])
    return out.outputs[0]


def main() -> None:
    fp_batch.install_addon()
    meshes = build()
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
    sc.fp_auto_merge = False
    sc.fp_auto_sharp = False
    sc.fp_sharp_auto = True
    sc.fp_min_island_area_pct = 0.3
    sc.fp_ridge_amount = 0.25
    sc.fp_ridge_radius = 0.08
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    sc.fp_line_sensitivity = 0.25

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
    if hasattr(sc.eevee, "gtao_distance"):
        sc.eevee.gtao_distance = r * AO_DIST
    if hasattr(sc.eevee, "fast_gi_distance"):
        sc.eevee.fast_gi_distance = r * AO_DIST

    sc.use_nodes = True
    tree = sc.node_tree
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    grp = next(n for n in tree.nodes if n.type == "GROUP")
    comp = next(n for n in tree.nodes
                if n.type in ("COMPOSITE", "OUTPUT_FILE") and
                n.type == "COMPOSITE")
    sa = next((n for n in tree.nodes if n.type == "SET_ALPHA"), None)

    # 強弱なしを先に撮る
    fp_batch.render_still(sc, OUT / "flat_nodes.png", 1)

    # グループの "line" 出力ではなく、いま合成に入っている線を拾う。
    # "line" は極性が逆(黒背景に白線)で、そのまま反転すると背景まで
    # 線として拾ってしまい全面真っ黒になった(実測: インク100%)。
    # 白プレビューやアンチエイリアスを通した後の絵が、Python版で
    # 測ったものと同じなので、そこを起点にする
    target = sa.inputs["Image"] if sa else comp.inputs[0]
    if not target.is_linked:
        raise SystemExit("合成に線が入っていない")
    line_sock = target.links[0].from_socket
    ao_sock = rl.outputs["AO"]
    weighted = build_weight(tree, line_sock, ao_sock)
    for lnk in list(target.links):
        tree.links.remove(lnk)
    tree.links.new(weighted, target)
    say(f"ノード数 {len(tree.nodes)}")
    fp_batch.render_still(sc, OUT / "weighted_nodes.png", 1)

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "ao_nodes.blend"))
    (OUT / "nodes.json").write_text(json.dumps(
        {"levels": LEVELS, "edges": EDGES, "bin": BIN, "gain": GAIN,
         "res": [RES_W, RES_H], "nodes": len(tree.nodes)},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
