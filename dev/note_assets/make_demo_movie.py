"""記事宣伝用の30秒デモ。ショットごとに連番を撮るところまで。

構成(24fps):
  hero    0.0-6.0s   同じ回転を「線なし」と「線あり」の2通りで撮る。
                     組み立て側でワイプして、同じ物であることを見せる
  montage 6.0-18.0s  5体を順に。全部回転しっぱなし
  split  18.0-23.0s  塗り分けと線を並べる。仕組みがそのまま見える
  title  23.0-30.0s  組み立て側で作る(Blender は使わない)

配布するのは 2.6.2 なので、2.6.2 のコードで撮ること。作業ツリーには
未公開の 2.7 が入っており、そちらで撮ると「動画では出ている線が、
買った版では出ない」ことになる。fp_batch を 2.6.2 の worktree から
import すれば、そこがアドオンとして読み込まれる。

    blender -b --factory-startup --python make_demo_movie.py -- \
        --fpbatch <2.6.2のworktree>/dev/batch [--shot hero]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


sys.path.insert(0, arg("--fpbatch",
                       str(Path(__file__).resolve().parents[1] / "batch")))
import fp_batch      # noqa: E402

OUT = Path(arg("--out", str(Path(__file__).resolve().parent / "out" / "demo")))
OUT.mkdir(parents=True, exist_ok=True)
RES_W = int(arg("--res", "1920"))
RES_H = int(RES_W * 9 / 16)
FPS = int(arg("--fps", "24"))
# 2倍で描いて縮める。線が細くなめらかになる
SS = int(arg("--ss", "2"))
ONLY = arg("--shot")
ROOT = Path(arg("--root", str(Path.home() / "blenderkit_data" / "models")))
T0 = time.time()

# 商標が明確なもの(バットモービル/アウディ/A320/NYPDカムリ)は外した
HERO = ("tank", "tank_2K_0fab3afc*")
MONTAGE = [
    ("c58", "jnr-c58-steam-locomotive_2K_d4845aae*"),
    ("kuka", "robot-kuka-quantec-with-palet-gripper_2K*"),
    ("ship", "dutch_ship_medium_2K_b67c0a0d*"),
    ("mech", "kaino-school-military-mech_2K_2fdfaccf*"),
    ("eiffel", "eiffel_tower_1892_4da8ea24*"),
]
SPLIT = ("camera", "camera_2K_d98f03a9*")

HERO_FRAMES = 144        # 6.0s
MONTAGE_FRAMES = 58      # 2.4s x 5 = 12.0s
SPLIT_FRAMES = 120       # 5.0s


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def find_blend(pattern):
    hits = sorted(ROOT.glob(f"*/{pattern}.blend"))
    return hits[0] if hits else None


def load(blend):
    """アセットを読み、外れジオメトリを隠して原点に正規化する。"""
    bpy.ops.wm.read_homefile(use_empty=True)
    meshes, others = fp_batch.append_objects(blend)
    if not meshes:
        raise RuntimeError("メッシュ無し")
    shape_names = set()
    for a in others:
        if a.type == "ARMATURE" and a.pose:
            for pb in a.pose.bones:
                if pb.custom_shape is not None:
                    shape_names.add(pb.custom_shape.name)
    for o in meshes:
        if (o.name in shape_names
                or o.name.lower().startswith(("cs_", "wgt", "shape_"))):
            o.hide_render = True
    content = [o for o in meshes if not o.hide_render] or meshes
    cluster = fp_batch.dominant_cluster(content)
    for o in content:
        if o not in cluster:
            o.hide_render = True
    framed = [o for o in content if o in cluster] or content
    fp_batch.normalize(meshes + others, framed)
    return meshes, others


def grey(meshes):
    """色を消して陰影だけ残す。線の有無だけが変わるようにする。"""
    mat = bpy.data.materials.new("FP_Demo")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    b = nt.nodes.new("ShaderNodeBsdfDiffuse")
    b.inputs["Color"].default_value = (0.62, 0.62, 0.61, 1.0)
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    o.location = (240, 0)
    nt.links.new(b.outputs["BSDF"], o.inputs["Surface"])
    for m in meshes:
        m.data.materials.clear()
        m.data.materials.append(mat)


def fit_distance(meshes, lens, margin=1.22):
    """被写体が縦横とも枠に収まる距離を出す。

    normalize() で 2m に揃えてはいるが、細長い物(機関車・エッフェル塔)は
    回すと幅が変わる。回転しても切れないよう、**水平半径**で見る。
    """
    import numpy as np
    pts = []
    for o in meshes:
        if o.hide_render:
            continue
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        return 4.0, 0.0
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    cz = (min(zs) + max(zs)) * 0.5
    # 回転させたときの最大の見かけ幅 = 水平方向の外接円の直径
    r = max(math.hypot(x, y) for x, y in zip(xs, ys))
    half_w = r * margin
    half_h = (max(zs) - min(zs)) * 0.5 * margin

    sensor_w = 36.0
    sensor_h = sensor_w * RES_H / RES_W
    d_w = half_w / math.tan(math.atan(sensor_w * 0.5 / lens))
    d_h = half_h / math.tan(math.atan(sensor_h * 0.5 / lens))
    return max(d_w, d_h), cz


def stage(meshes):
    """カメラとライト。カメラを空の子にして、空を回すと周回する。"""
    sc = bpy.context.scene
    lens = 55.0
    dist, cz = fit_distance(meshes, lens)
    piv = bpy.data.objects.new("Pivot", None)
    sc.collection.objects.link(piv)
    piv.location = (0.0, 0.0, cz)
    cd = bpy.data.cameras.new("C")
    cd.lens = lens
    cd.clip_start = 0.01
    cd.clip_end = dist * 20.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.parent = piv
    # やや見下ろす。真正面より立体が分かる
    cam.location = (0.0, -dist * 0.94, dist * 0.34)
    look = Vector((0.0, 0.0, 0.0)) - Vector(cam.location)
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()

    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.44, 0.45, 0.48, 1.0)
        bg.inputs[1].default_value = 0.6
    sc.world = w
    # 光量は被写体までの距離で決まる。距離に比例させないと、
    # 大きい物と小さい物で露出が揃わない(戦車が白飛びした)
    k = dist * dist
    for name, off, energy, size in (
            ("Key", (0.75, -0.85, 0.95), 8.5, 1.4),
            ("Fill", (-0.9, -0.55, 0.35), 2.6, 1.8)):
        lt = bpy.data.lights.new(name, type="AREA")
        lt.energy = energy * k
        lt.size = size * dist * 0.5
        lo = bpy.data.objects.new(name, lt)
        sc.collection.objects.link(lo)
        lo.location = tuple(v * dist for v in off)
        aim = Vector((0.0, 0.0, 0.0)) - Vector(lo.location)
        lo.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
        lo.parent = piv
    return piv


def setup_lines(meshes):
    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = False
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    return time.time() - t


def paint_material():
    mat = bpy.data.materials.new("VC")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "mecha_color"
    em = nt.nodes.new("ShaderNodeEmission")
    ou = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
    return mat


def render_seq(tag, piv, n_frames, modes, spin, start_deg=32.0):
    """回しながら撮る。modes は plain(線なし) / line / paint(塗り分け)。"""
    sc = bpy.context.scene
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    # render_still(ss) は「シーンの解像度で描いてから 1/ss に縮める」関数。
    # 解像度を ss 倍にするのは呼ぶ側の仕事で、ここを等倍にしていると
    # 出来上がりが 1/ss になる(博物館の動画で踏んだ)
    sc.render.resolution_x = RES_W * SS
    sc.render.resolution_y = RES_H * SS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"

    meshes = [o for o in sc.objects if o.type == "MESH"]
    saved = {o.name: [s.material for s in o.material_slots] for o in meshes}
    pmat = paint_material() if "paint" in modes else None

    for mode in modes:
        d = OUT / f"{tag}_{mode}"
        d.mkdir(parents=True, exist_ok=True)
        sc.use_nodes = (mode == "line")
        keep_view = sc.view_settings.view_transform
        if mode == "paint":
            for o in meshes:
                for s in o.material_slots:
                    s.material = pmat
            sc.view_settings.view_transform = 'Standard'
        for f in range(n_frames):
            piv.rotation_euler = (0.0, 0.0, math.radians(
                start_deg + 360.0 * spin * f / n_frames))
            bpy.context.view_layer.update()
            fp_batch.render_still(sc, d / f"f{f:04d}.png", SS)
        if mode == "paint":
            sc.view_settings.view_transform = keep_view
            for o in meshes:
                for s, m in zip(o.material_slots, saved[o.name]):
                    s.material = m
        say(f"  {tag}/{mode} {n_frames}枚")


def shot(tag, pattern, n_frames, modes, spin):
    blend = find_blend(pattern)
    if blend is None:
        say(f"{tag}: 見つからない ({pattern})")
        return None
    meshes, _others = load(blend)
    grey(meshes)
    piv = stage(meshes)
    sec = setup_lines(meshes)
    nf = sum(len(o.data.polygons) for o in meshes if not o.hide_render)
    say(f"{tag}: 面{nf:,} STEP0 {sec:.1f}秒")
    render_seq(tag, piv, n_frames, modes, spin)
    return {"tag": tag, "faces": nf, "step0": round(sec, 1),
            "frames": n_frames, "modes": modes}


def main():
    fp_batch.install_addon()
    rows = []
    if ONLY in (None, "hero"):
        r = shot(HERO[0], HERO[1], HERO_FRAMES, ["plain", "line"], 0.5)
        if r:
            rows.append(r)
    if ONLY in (None, "montage"):
        for name, pat in MONTAGE:
            r = shot(name, pat, MONTAGE_FRAMES, ["line"], 0.34)
            if r:
                rows.append(r)
    if ONLY in (None, "split"):
        r = shot(SPLIT[0], SPLIT[1], SPLIT_FRAMES, ["paint", "line"], 0.5)
        if r:
            rows.append(r)
    (OUT / "shots.json").write_text(
        json.dumps({"fps": FPS, "res": [RES_W, RES_H], "ss": SS,
                    "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
