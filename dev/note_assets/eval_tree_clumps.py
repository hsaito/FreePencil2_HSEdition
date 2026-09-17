"""木(葉カード)のつぶれ: 葉を「房」にまとめて塗る案を総当りする(試作)。

葉カードは1枚ずつ別のルースパーツ = 別の島で、近接隣接で互いに違う色に
なるため、葉1枚ごとに輪郭が出て遠くでは黒い塊になる。人が木を描くときは
葉を1枚ずつ描かず、房(かたまり)の輪郭を描く。それを塗り分けで再現する:

    小さいルースパーツ(葉)を 3D 位置で K 個の房に分け、房ごとに1色。
    房の中には線が出ず、房と房の境と、木の輪郭だけが線になる。

本体は触らず、STEP0 の後で mecha_color を書き換えて撮る。

    K = current(今のまま) / 1 / 4 / 8 / 16 / 32
    距離 = 近(画面いっぱい) / 遠(高さ 1/5)

  blender -b --factory-startup --python eval_tree_clumps.py -- \
      [--only tree_autumn,coconut] [--res 1920] [--ks 1,4,8,16,32]
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "tree_clumps"))).resolve()
RES = int(arg("--res", "1920"))
ONLY = arg("--only", "tree_autumn,coconut-tree,european-maple,manchester-acacia")
KS = [int(k) for k in arg("--ks", "1,4,8,16,32").split(",") if k]
GAPS = [int(g) for g in arg("--gaps", "").split(",") if g]        # 隙間埋め px(200%)
KS_GAP = [int(k) for k in arg("--ks-gap", "8").split(",") if k]   # 隙間埋めと組む K
MONO_FLOOR = float(arg("--floor", "0.55"))
SMALL_PCT = float(arg("--small", "1.0"))     # 葉と見なすパーツの面積(全体比 %)
CH_DEPTH = float(arg("--ch-depth", "1.0"))   # 深度チャンネル(町のデモは 0)

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


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# ---------------------------------------------------------------- 房分け

def leaf_parts(obj):
    """STEP1 が塗った島(同じ色で辺がつながる面の連結成分)と、その面積・面の対応。

    最初はルースパーツ(頂点の連結成分)で見ていたが、ヤシの葉は葉柄で
    つながった1枚のメッシュで、小葉は鋭角で切られた「島」だった。
    パーツで見ると何も変わらない(実測)。隣り合う島は必ず違う色なので、
    「同じ色で辺を共有する面」をたどれば STEP1 の島がそのまま戻る。
    """
    from freepencil2 import mesh_islands
    me = obj.data
    nv, ne, nf, nl = len(me.vertices), len(me.edges), len(me.polygons), len(me.loops)
    if nv == 0 or ne == 0 or nf == 0:
        return None
    vc = me.color_attributes.get("mecha_color")
    if vc is None:
        return None
    buf = np.empty(nl * 4, dtype=np.float32)
    vc.data.foreach_get("color", buf)
    buf = buf.reshape(-1, 4)
    starts = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_start", starts)
    totals = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_total", totals)
    q = np.round(buf[starts, :3] * 255.0).astype(np.int64)
    colid = q[:, 0] * 65536 + q[:, 1] * 256 + q[:, 2]
    loop_edge = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("edge_index", loop_edge)
    loop_face = np.repeat(np.arange(nf, dtype=np.int32), totals)
    order = np.argsort(loop_edge, kind="stable")
    le, lf = loop_edge[order], loop_face[order]
    same = le[1:] == le[:-1]
    fa, fb = lf[:-1][same], lf[1:][same]
    keep = colid[fa] == colid[fb]
    part_of_face = mesh_islands.connected_components(fa[keep], fb[keep], nf)
    area = np.empty(nf, dtype=np.float32)
    me.polygons.foreach_get("area", area)
    center = np.empty(nf * 3, dtype=np.float32)
    me.polygons.foreach_get("center", center)
    center = center.reshape(-1, 3)
    n_parts = int(part_of_face.max()) + 1
    part_area = np.bincount(part_of_face, weights=area, minlength=n_parts)
    return part_of_face, part_area, center


def kmeans(pts, k, seed, iters=25):
    rng = np.random.default_rng(seed)
    k = min(k, len(pts))
    # k-means++ 風の初期化
    ctr = [pts[rng.integers(len(pts))]]
    for _ in range(1, k):
        d = np.min(((pts[:, None, :] - np.asarray(ctr)[None, :, :]) ** 2).sum(-1), axis=1)
        d = d.astype(np.float64)
        if d.sum() <= 0.0:
            break
        p = d / d.sum()
        ctr.append(pts[rng.choice(len(pts), p=p / p.sum())])
    ctr = np.asarray(ctr)
    lab = np.zeros(len(pts), dtype=np.int64)
    for _ in range(iters):
        d = ((pts[:, None, :] - ctr[None, :, :]) ** 2).sum(-1)
        lab = d.argmin(axis=1)
        for j in range(k):
            m = lab == j
            if m.any():
                ctr[j] = pts[m].mean(axis=0)
    return lab, ctr


def clump_colors(obj, k, seed=42):
    """葉パーツを k 房に分けて房ごとに1色を mecha_color に書く。戻り値は葉パーツ数。"""
    from freepencil2 import utils
    got = leaf_parts(obj)
    if got is None:
        return 0
    part_of_face, part_area, center = got
    total = float(part_area.sum())
    small = part_area < total * SMALL_PCT / 100.0
    leaf_ids = np.nonzero(small)[0]
    if len(leaf_ids) < 50:
        return 0
    is_leaf_face = small[part_of_face]
    # パーツの重心(面の中心の平均、ワールド)
    mw = np.asarray(obj.matrix_world.to_3x3(), dtype=np.float32)
    tr = np.asarray(obj.matrix_world.translation, dtype=np.float32)
    cw = center @ mw.T + tr
    n_parts = len(part_area)
    sx = np.bincount(part_of_face, weights=cw[:, 0], minlength=n_parts)
    sy = np.bincount(part_of_face, weights=cw[:, 1], minlength=n_parts)
    sz = np.bincount(part_of_face, weights=cw[:, 2], minlength=n_parts)
    cnt = np.bincount(part_of_face, minlength=n_parts).astype(np.float64)
    pc = np.stack([sx, sy, sz], axis=1) / np.maximum(cnt, 1)[:, None]
    pts = pc[leaf_ids]
    if k <= 1:
        lab = np.zeros(len(leaf_ids), dtype=np.int64)
        ctr = pts.mean(axis=0, keepdims=True)
    else:
        lab, ctr = kmeans(pts, k, seed)
    kk = len(ctr)
    # 房の隣接: 近い4房を隣とする(対称)
    neighbors = [set() for _ in range(kk)]
    if kk > 1:
        d = ((ctr[:, None, :] - ctr[None, :, :]) ** 2).sum(-1)
        for i in range(kk):
            for j in np.argsort(d[i])[1:min(5, kk)]:
                neighbors[i].add(int(j))
                neighbors[int(j)].add(i)
    neighbors = [sorted(s) for s in neighbors]
    classes = utils.color_graph_greedy(neighbors)
    n_classes = max(classes) + 1
    palette, _, _ = utils.palette_for_diversity(0.5, max(kk, n_classes), seed,
                                                min_k=n_classes)
    classes, _ = utils.diversify_island_colors(neighbors, classes, palette, 0.5)
    col = np.asarray([palette[c][:3] for c in classes], dtype=np.float32)
    # 面 -> 房 -> 色
    part_to_clump = np.full(n_parts, -1, dtype=np.int64)
    part_to_clump[leaf_ids] = lab
    face_clump = part_to_clump[part_of_face]
    me = obj.data
    vc = me.color_attributes.get("mecha_color")
    nl = len(me.loops)
    buf = np.empty(nl * 4, dtype=np.float32)
    vc.data.foreach_get("color", buf)
    buf = buf.reshape(-1, 4)
    totals = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_total", totals)
    loop_face = np.repeat(np.arange(len(me.polygons), dtype=np.int32), totals)
    sel = is_leaf_face[loop_face]
    buf[sel, :3] = col[face_clump[loop_face][sel]]
    vc.data.foreach_set("color", buf.reshape(-1))
    me.update()
    return len(leaf_ids)


# ---------------------------------------------------------------- 隙間埋め

GAP_LABEL = "FP_EVAL_GAP"


def gap_fill(sc, px):
    """葉の隙間(背景が透ける穴)を線にしない: AOV の穴を Inpaint で埋める。

    穴の縁は「葉の色 -> 背景の黒」の差で線になる。ヤシの葉や針葉樹は
    葉の間から空が見えるので、葉1枚ごとに輪郭が出て黒くなる。
    グループに入る前の mecha_color を
        Set Alpha(AOV, alpha) -> Inpaint(px) -> x 閉じたalpha
    に置き換える。px より狭い穴だけ埋まり、外側の輪郭は動かない
    (閉じ = 膨張してから収縮)。px=0 で元に戻す。
    """
    from freepencil2 import compat, line_weight
    tree = compat.get_compositor_tree(sc)
    for n in [n for n in tree.nodes if n.label == GAP_LABEL]:
        tree.nodes.remove(n)
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    gnode = next(n for n in tree.nodes if n.type == "GROUP")
    src = rl.outputs.get("mecha_color")
    dst = gnode.inputs.get("mecha_color")
    dst_a = gnode.inputs.get("Alpha")
    for lk in list(dst.links) + list(dst_a.links):
        tree.links.remove(lk)
    if px <= 0:
        tree.links.new(src, dst)
        tree.links.new(rl.outputs["Alpha"], dst_a)
        return
    x, y = gnode.location.x - 700, gnode.location.y - 900

    def new(idn, dx, dy):
        n = tree.nodes.new(idn)
        n.label = GAP_LABEL
        n.location = (x + dx, y + dy)
        return n
    sa = new("CompositorNodeSetAlpha", 0, 0)
    compat.set_node_value(sa, "mode", "REPLACE_ALPHA")
    tree.links.new(src, sa.inputs["Image"])
    tree.links.new(rl.outputs["Alpha"], sa.inputs["Alpha"])
    ip = new("CompositorNodeInpaint", 160, 0)
    if hasattr(ip, "distance"):
        ip.distance = int(px)
    else:
        line_weight._set_num_socket(ip, "Size", int(px))
    tree.links.new(sa.outputs[0], ip.inputs[0])
    dil = new("CompositorNodeDilateErode", 160, -160)
    line_weight._set_dilate(dil, int(px))
    tree.links.new(rl.outputs["Alpha"], dil.inputs[0])
    ero = new("CompositorNodeDilateErode", 320, -160)
    line_weight._set_dilate(ero, -int(px))
    tree.links.new(dil.outputs[0], ero.inputs[0])
    mix = new("CompositorNodeMixRGB", 480, 0)
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    tree.links.new(ip.outputs[0], mix.inputs[1])
    tree.links.new(ero.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], dst)
    # グループは Alpha で白に載せてから検出するので、穴を埋めた alpha も渡す
    tree.links.new(ero.outputs[0], dst_a)


# ---------------------------------------------------------------- 撮る

def stage(meshes, far_mult):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes
           for c in o.bound_box if not o.hide_render]
    xs, ys, zs = ([p[i] for p in pts] for i in range(3))
    ctr = Vector(((min(xs) + max(xs)) * .5, (min(ys) + max(ys)) * .5, (min(zs) + max(zs)) * .5))
    r = max((p - ctr).length for p in pts)
    cam = sc.camera
    if cam is None:
        cd = bpy.data.cameras.new("C")
        cd.lens = 40.0
        cam = bpy.data.objects.new("C", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
        w = bpy.data.worlds.new("W")
        w.use_nodes = True
        bg = w.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[0].default_value = (.5, .5, .52, 1)
            bg.inputs[1].default_value = .15
        sc.world = w
        lt = bpy.data.lights.new("K", type="SUN")
        lt.energy = 3.0
        lt.angle = math.radians(2.0)
        lo = bpy.data.objects.new("K", lt)
        sc.collection.objects.link(lo)
        lo.rotation_euler = (math.radians(50), 0, math.radians(-35))
    a = math.radians(25.0)
    from bpy_extras.object_utils import world_to_camera_view

    def place(d):
        cam.location = (ctr.x + math.sin(a) * d, ctr.y - math.cos(a) * d, ctr.z + d * 0.05)
        cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    d = r * 3.0
    for _ in range(3):
        place(d)
        m = max(max(abs(world_to_camera_view(sc, cam, p).x - .5) * 2,
                    abs(world_to_camera_view(sc, cam, p).y - .5) * 2) for p in pts)
        d *= m * 1.05
    place(d * far_mult)
    cam.data.clip_end = d * far_mult * 30


def run_model(path, name):
    meshes, _ = dm.load(path)
    dm.grey(meshes)
    sc = bpy.context.scene
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.fp_auto_style = 'WEIGHTED'
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    stage(meshes, 1.0)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert sc.render.resolution_percentage == 200
    sc.fp_ch_depth = CH_DEPTH
    sc.fp_mono_floor = MONO_FLOOR
    sc.fp_preview_mode = 'MONO_LIGHT'
    # 元の色を控えて、K ごとに戻してから書く
    orig = {}
    for o in meshes:
        vc = o.data.color_attributes.get("mecha_color")
        if vc is not None:
            b = np.empty(len(o.data.loops) * 4, dtype=np.float32)
            vc.data.foreach_get("color", b)
            orig[o.name] = b
    variants = [("current", 0, 0)] + [(f"k{k}", k, 0) for k in KS]
    variants += [(f"k{k}_gap{g}", k, g) for k in KS_GAP for g in GAPS]
    for tag, k, gap in variants:
        for o in meshes:
            if o.name in orig:
                o.data.color_attributes["mecha_color"].data.foreach_set("color", orig[o.name])
                o.data.update()
        if k > 0:
            n = sum(clump_colors(o, k) for o in meshes if o.name in orig)
            say(f"  {name} {tag}: 葉パーツ {n}")
        gap_fill(sc, gap)
        for dist, mult in (("near", 1.0), ("far", 5.0)):
            stage(meshes, mult)
            fp_batch.render_still(sc, OUT / f"{name}_{tag}_{dist}.png", 1)
        say(f"  {name} {tag} 撮った")


def main():
    fp_batch.install_addon()
    pats = [x for x in ONLY.split(",") if x]
    models = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
              if any(p in Path(m["path"]).stem for p in pats)]
    for m in models:
        name = Path(m["path"]).stem[:20]
        try:
            run_model(m["path"], name)
        except Exception as e:                       # noqa: BLE001
            import traceback
            traceback.print_exc()
            say(f"{name}: 失敗 {type(e).__name__}: {e}")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
