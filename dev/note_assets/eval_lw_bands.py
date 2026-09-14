"""段分けが本当に 20% ずつになっているかを、コンポジタの中の値で確かめる。

しきい値は measure_edges が「線の画素における d = 1-AO の分位点」として
測る。段分けはコンポジタの中で「ぼかした AO から作った d」で行う。
この2つが同じ分布なら各段に 20% ずつ入るはずで、違えば偏る。

k=4(深い側)だけを 12px にしたら頭頂まで 2倍以上太った(実測)ので、
ほぼ全部の線画素が k=4 に入っている疑いがある。

STEP3 が組んだノードの dep を File Output で書き出し、線の芯(binz)
の画素における分位点と、実際に使われた edges を並べる。

  blender -b --factory-startup --python eval_lw_bands.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "lw_bands"
sys.argv = ["blender", "--", "--out", str(OUT), "--res", "1400", "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
RES = 1400


def say(m):
    print(f"@@@ {m}", flush=True)


def load_exr(p):
    img = bpy.data.images.load(str(p))
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, 4)[..., 0].copy()
    finally:
        bpy.data.images.remove(img)


def main():
    fp_batch.install_addon()
    from freepencil2 import compat, line_weight
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("S", "SUBSURF")
    m.levels = m.render_levels = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    dm.grey([o])
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("C")
    cd.lens = 70.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tgt = Vector((0, 0, 0.1))
    a, e, d = math.radians(20), math.radians(8), 5.2
    cam.location = (tgt.x + math.sin(a) * math.cos(e) * d,
                    tgt.y - math.cos(a) * math.cos(e) * d,
                    tgt.z + math.sin(e) * d)
    cam.rotation_euler = (tgt - Vector(cam.location)).to_track_quat(
        "-Z", "Y").to_euler()
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(62), 0, math.radians(40))
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview",
               "fp_auto_supersample", "fp_supersample"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.fp_white_preview = True
    sc.fp_auto_style = 'WEIGHTED'    # STEP0 が強弱・14度・稜線0.45・しきい値計測を入れる
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = sc.render.resolution_y = RES * 2
    sc.render.film_transparent = True
    bpy.ops.freepencil.measure_line_weight()
    edges = [float(getattr(sc, f"fp_lw_e{i}")) for i in range(1, 5)]
    say(f"measure_edges が決めたしきい値 {[round(x, 4) for x in edges]}")
    bpy.ops.freepencil2.link_button()
    sc.fp_white_preview = True

    # STEP3 が組んだ dep(1-AO) と binz(線の芯) を書き出す
    tree = compat.get_compositor_tree(sc)
    dep = binz = None
    for n in tree.nodes:
        if n.label != line_weight.NODE_LABEL or n.type != "MATH":
            continue
        if n.operation == "SUBTRACT" and abs(n.inputs[0].default_value - 1.0) < 1e-6 \
                and n.inputs[1].links and n.inputs[1].links[0].from_node.type == "BLUR":
            dep = n
        if n.operation == "GREATER_THAN" and n.inputs[0].links \
                and n.inputs[0].links[0].from_node.type == "INVERT" and binz is None:
            binz = n
    if dep is None or binz is None:
        raise SystemExit(f"ノードが見つからない dep={dep} binz={binz}")
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    if hasattr(fo, "base_path"):
        fo.base_path = str(OUT)
    else:
        fo.directory = str(OUT)
    slots = fo.file_slots if hasattr(fo, "file_slots") else fo.file_output_items
    slots[0].path = "dep"
    slots.new("binz")
    tree.links.new(dep.outputs[0], fo.inputs[0])
    tree.links.new(binz.outputs[0], fo.inputs[1])
    bpy.ops.render.render(write_still=False)
    D = load_exr(next(OUT.glob("dep*.exr")))
    B = load_exr(next(OUT.glob("binz*.exr")))
    line = B > 0.5
    v = D[line]
    say(f"線の芯 {int(line.sum())} 画素  dep 分位点 20/40/60/80 = "
        f"{[round(float(np.percentile(v, q)), 4) for q in (20, 40, 60, 80)]}")
    k = np.digitize(v, edges)
    share = [round(float((k == i).mean()) * 100, 1) for i in range(5)]
    say(f"実際に各段へ入った割合 k=0..4 : {share} %  (20% ずつのはず)")


if __name__ == "__main__":
    main()
