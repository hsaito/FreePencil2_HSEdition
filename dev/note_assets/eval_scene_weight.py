"""複数モデルを並べたシーンで、線の太さの付け方を試す素材を撮る。

見たいことは2つ。

  1. オブジェクトが複数あるとき、外形(重なりを含む)が深度チャンネルで
     ちゃんと拾えるか。1体だけのときは拾えていた。
  2. 仮想ライトの陰影を使い、暗いところの線を太くできるか。
     線画では影側の線を重くするのが定石。

出すもの:
    ch_all.png    全チャンネル
    ch_depth.png  深度だけ = 外形と重なり
    ch_mecha.png  メカだけ = 内側
    shade.png     陰影のみ (仮想ライト1灯)。暗さを太さの手掛かりにする

  blender -b --factory-startup --python eval_scene_weight.py -- \
      --out <dir> [--res 1400]
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
OUT = Path(arg("--out", str(HERE / "out" / "scene"))).resolve()
RES_W = int(arg("--res", "1400"))
SS = int(arg("--ss", "1"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W),
            "--ss", str(SS)]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
from mathutils import Vector      # noqa: E402
import fp_batch                   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()

# 手前から奥へ重なるように置く。重なりの線が出るかを見たい
MODELS = [
    ("toytrain", "toy_train-02*", (-3.0, 0.8, 0.0)),
    ("generator", "portable-generat*", (0.0, 0.0, 0.0)),
    ("scavenger", "space_scavenger*", (3.0, 0.8, 0.0)),
]
# 物ごとの色。隣り合う物が同じ色にならない程度に散らす
ID_COLORS = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1),
             (0, 1, 1), (1, 0.5, 0), (0.5, 0, 1), (0, 1, 0.5), (0.6, 0.6, 0.6)]
CHANNELS = ["fp_ch_mecha", "fp_ch_depth", "fp_ch_bone", "fp_ch_gen",
            "fp_ch_mat"]


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def place(pattern: str, loc=None):
    """1体を読み込み、大きさをそろえて指定位置へ置く。

    dm.load はシーンを消してしまうので使えない。append して自前で
    正規化する。
    """
    blend = dm.find_blend(pattern)
    if blend is None:
        say(f"見つからない: {pattern}")
        return [], []
    # append_objects はシーン内の全メッシュを返す。差分を取らないと
    # 2体目を読んだとき1体目も一緒に動いてしまう
    # (実測: 3体が x=14, 30, 32 に散り、絵が高さ 67px の帯になった)
    before = set(bpy.data.objects)
    all_meshes, all_others = fp_batch.append_objects(blend)
    fresh = set(bpy.data.objects) - before
    meshes = [o for o in all_meshes if o in fresh]
    others = [o for o in all_others if o in fresh]
    if not meshes:
        return [], []
    shape = set()
    for a in others:
        if a.type == "ARMATURE" and a.pose:
            for pb in a.pose.bones:
                if pb.custom_shape is not None:
                    shape.add(pb.custom_shape.name)
    for o in meshes:
        if o.name in shape or o.name.lower().startswith(("cs_", "wgt", "shape_")):
            o.hide_render = True
    content = [o for o in meshes if not o.hide_render] or meshes
    cluster = fp_batch.dominant_cluster(content)
    for o in content:
        if o not in cluster:
            o.hide_render = True
    framed = [o for o in content if o in cluster] or content
    fp_batch.normalize(meshes + others, framed)

    bpy.context.view_layer.update()
    return meshes, list(others)


def group_bounds(meshes):
    """グループの見た目の範囲(ワールド座標)を返す。"""
    pts = []
    for o in meshes:
        if o.hide_render:
            continue
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        return None
    xs = [p.x for p in pts]
    return min(xs), max(xs)


def shift(meshes, others, dx: float) -> None:
    """グループを横へずらす。

    親を持つ子まで動かすと、親の分と二重に足されて散らばる
    (実測: 3体が横 34 単位に広がり、絵が高さ 67px の帯になった)。
    このグループの中に親がいないものだけを動かす。
    """
    group = set(meshes) | set(others)
    for o in group:
        if o.parent not in group:
            o.location = (o.location[0] + dx, o.location[1], o.location[2])
    bpy.context.view_layer.update()


def stage_all(meshes) -> None:
    """全部が枠に収まるカメラと、仮想ライト1灯。"""
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    pts = []
    for o in meshes:
        if o.hide_render:
            continue
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    cx, cz = (min(xs) + max(xs)) * 0.5, (min(zs) + max(zs)) * 0.5
    lens = 55.0
    half_w = (max(xs) - min(xs)) * 0.5 * 1.14
    half_h = (max(zs) - min(zs)) * 0.5 * 1.14
    sensor_w = 36.0
    sensor_h = sensor_w * RES_H / RES_W
    d = max(half_w / math.tan(math.atan(sensor_w * 0.5 / lens)),
            half_h / math.tan(math.atan(sensor_h * 0.5 / lens)))
    d = max(d, (max(ys) - min(ys)) * 1.5)
    cd = bpy.data.cameras.new("C")
    cd.lens = lens
    cd.clip_end = d * 20
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (cx, min(ys) - d, cz + d * 0.12)
    look = Vector((cx, 0.0, cz)) - Vector(cam.location)
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()

    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1.0)
        bg.inputs[1].default_value = 0.35   # 暗めにして陰影を出す
    sc.world = w
    # 仮想ライトは1灯だけ。左上から。影側がはっきり出る向きにする
    lt = bpy.data.lights.new("Key", type="SUN")
    lt.energy = 4.0
    lo = bpy.data.objects.new("Key", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(58), 0.0, math.radians(38))


def only(scene, keep) -> None:
    for n in CHANNELS:
        if hasattr(scene, n):
            setattr(scene, n, 1.0 if (keep is None or n == keep) else 0.0)


def main() -> None:
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)
    meshes = []
    cursor = 0.0
    for tag, pat, _loc in MODELS:
        got, others = place(pat, None)
        if not got:
            continue
        b = group_bounds(got)
        if b is None:
            continue
        # 直前の右端の続きに置く。ずらす前の値で次の位置を決めると
        # 実際の移動量とずれて重なる。動かしたあとに測り直す
        shift(got, others, cursor - b[0] + 0.35)
        b2 = group_bounds(got)
        cursor = b2[1] + 0.7
        say(f"{tag}: メッシュ {len(got)} 幅 {b2[1] - b2[0]:.2f} "
            f"x {b2[0]:.2f}..{b2[1]:.2f}")
        meshes += got
    if not meshes:
        raise SystemExit("モデルが1つも置けなかった")
    dm.grey(meshes)
    stage_all(meshes)

    sc = bpy.context.scene
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
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    say(f"STEP0 {time.time() - t:.1f}秒 / メッシュ {len(meshes)}")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W * SS
    sc.render.resolution_y = RES_H * SS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    sc.use_nodes = True
    for keep, name in ((None, "ch_all.png"), ("fp_ch_depth", "ch_depth.png"),
                       ("fp_ch_mecha", "ch_mecha.png")):
        only(sc, keep)
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, OUT / name, SS)
        say(f"  {name}")
    only(sc, None)

    # 陰影のみ。白マテリアルを外して、仮想ライトの明暗をそのまま撮る
    sc.use_nodes = False
    sc.fp_white_preview = False
    fp_batch.render_still(sc, OUT / "shade.png", SS)
    say("  shade.png")

    # オブジェクトID。物ごとに違う色を発光で塗る。色が変わるところが
    # 「物と物の境目」。深度と違い、接していて奥行きが同じでも出る
    saved = {o.name: [s2.material for s2 in o.material_slots] for o in meshes}
    keep_vt = sc.view_settings.view_transform
    sc.view_settings.view_transform = "Standard"
    for i, o in enumerate(meshes):
        col = ID_COLORS[i % len(ID_COLORS)]
        mat = bpy.data.materials.new(f"ID_{i}")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*col, 1.0)
        ou = nt.nodes.new("ShaderNodeOutputMaterial")
        ou.location = (240, 0)
        nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
        o.data.materials.clear()
        o.data.materials.append(mat)
    fp_batch.render_still(sc, OUT / "objid.png", SS)
    say("  objid.png")
    sc.view_settings.view_transform = keep_vt
    for o in meshes:
        o.data.materials.clear()
        for m in saved[o.name]:
            o.data.materials.append(m)

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene.blend"))
    (OUT / "scene.json").write_text(json.dumps(
        {"models": [m[0] for m in MODELS], "res": [RES_W, RES_H]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
