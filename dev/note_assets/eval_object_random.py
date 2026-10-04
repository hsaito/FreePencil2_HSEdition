"""リンク複製を「オブジェクトごとに違う色」にできるかの試作。

分かったこと: パーツごとの色味(fp_part_tint)はオブジェクト単位で決めた
明度クラスを、頂点カラーとしてメッシュに書き込んでいる。メッシュを
共有するリンク複製(卵75個 = 4メッシュ)では、書き込む先が同じなので
原理的に色を変えられない。近接隣接も同じ理由で効かない。

逃げ道: シェーダには Object Info の Random がある。オブジェクトごとに
違う値が来るので、メッシュを増やさずに色をずらせる。AOV へ届く手前に
掛ければ、線の検出側にもその差が届くはず。

ここでは本体を触らず、STEP0/2 のあとにマテリアルへ差し込んで試す。
効くなら、v2.8 の機能として設計する価値がある。

  blender -b --factory-startup --python eval_object_random.py -- \
      [--res 900] [--amount 0.25]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "obj_random"))).resolve()
RES = int(arg("--res", "900"))
FLOOR = float(arg("--floor", "14.0"))
RIDGE = float(arg("--ridge", "0.45"))

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
AOV_GROUP = "FreePencil_aov_Group_v1_1_0"


def say(m):
    print(f"@@@ {m}", flush=True)


def inject(amount: float) -> int:
    """AOV グループの中で、塗り分けの色にオブジェクトごとの倍率を掛ける。

    グループの中は
        Color Attribute(mecha_color) -> Mix.002.A -> Mix.005.A -> AOV
    で、passthrough_aov_color が Mix の Factor を 0 にしているので
    頂点カラーが素通しで AOV へ出る。その入口で明度をずらす。

    色相を回すと隣接島の色距離の意味が変わるので、まずは明度だけ。
    倍率は (1-amount) .. (1+amount) の範囲にオブジェクトごとに散る。
    グループは全マテリアルで共有だが、Object Info はシェーディング点
    ごとに評価されるので、共有していてもオブジェクトごとに違う値が来る。
    """
    from freepencil2 import utils_nodegroup
    ng = utils_nodegroup.ensure_node_group_updated(AOV_GROUP)
    src = ng.nodes.get("Color Attribute")
    dst = ng.nodes.get("Mix.002")
    if src is None or dst is None:
        return 0
    link = next((l for l in ng.links
                 if l.from_node == src and l.to_node == dst), None)
    if link is None:
        return 0
    to_sock = link.to_socket
    ng.links.remove(link)
    info = ng.nodes.new("ShaderNodeObjectInfo")
    info.location = (src.location.x - 240, src.location.y - 260)
    mad = ng.nodes.new("ShaderNodeMath")
    mad.operation = "MULTIPLY_ADD"
    mad.location = (src.location.x - 60, src.location.y - 260)
    mad.inputs[1].default_value = 2.0 * amount
    mad.inputs[2].default_value = 1.0 - amount
    comb = ng.nodes.new("ShaderNodeCombineColor")
    comb.location = (src.location.x + 110, src.location.y - 260)
    mul = ng.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.location = (src.location.x + 260, src.location.y - 120)
    mul.inputs["Factor"].default_value = 1.0
    ng.links.new(info.outputs["Random"], mad.inputs[0])
    for k in ("Red", "Green", "Blue"):
        ng.links.new(mad.outputs[0], comb.inputs[k])
    ng.links.new(src.outputs["Color"], mul.inputs[6])    # A
    ng.links.new(comb.outputs[0], mul.inputs[7])         # B
    ng.links.new(mul.outputs[2], to_sock)
    return 1


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


def run(path, amount, tag):
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
    sc.fp_auto_split_floor = FLOOR
    sc.fp_auto_merge = False
    sc.fp_min_island_area_pct = 1.0
    sc.fp_ridge_amount = RIDGE
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
    if amount > 0.0:
        say(f"  差し込んだマテリアル {inject(amount)}")
    sc.fp_white_preview = True
    fp_batch.render_still(sc, OUT / f"{tag}.png", 2)
    say(f"{tag} (ずらし{amount}) 完了")


def main():
    fp_batch.install_addon()
    path = next(m["path"] for m in scan_models.scan(scan_models.DEFAULT_ROOT)
                if "eggs_bowl" in Path(m["path"]).stem)
    for amt, tag in ((0.0, "a_off"), (0.12, "b_012"),
                     (0.25, "c_025"), (0.40, "d_040")):
        run(path, amt, tag)


if __name__ == "__main__":
    main()
