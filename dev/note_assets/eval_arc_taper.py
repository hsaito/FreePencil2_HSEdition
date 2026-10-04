"""入り抜きをメッシュ上で作る実験。島の境界から「形の太さ」を測る。

画像の上で試した方法(曲率・密度・形の太さ)は、どれも他の線が混ざって
失敗した。メッシュの上なら島ごとに独立して測れる。

測り方:
    1. STEP0 が焼いた mecha_color から島を復元する。
       線は色の境目から出るので、こうすれば線と島が必ず一致する。
    2. 島ごとに、境界の頂点を始点にして内側へ測地距離を伸ばす。
    3. 各頂点がどの境界頂点から来たかを記録し、境界頂点に
       「自分が担当した最大の深さ」を持ち帰らせる。
       これが、その境界における形の太さ(内接円の半径)になる。
    4. 島の中で 0..1 に正規化して頂点カラーに書く。

  毛先では担当する深さが浅いので小さく、束の中ほどでは中心線まで
  担当するので大きい。これが入り抜きの手掛かりになる。

出すもの:
    line.png   線画
    thick.png  形の太さ(白いほど太い形)
    plain.png  陰影

  blender -b --factory-startup --python eval_arc_taper.py -- \
      --out <dir> --model <pattern> [--res 3840]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "arc"))).resolve()
RES_W = int(arg("--res", "3840"))
MODEL = arg("--model", "loli_anime_girl*")
ATTR = "fp_thick"

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W), "--ss", "1"]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def face_colors(mesh, name="mecha_color"):
    """面ごとの色を返す。角の色の平均を取る。"""
    lay = mesh.color_attributes.get(name)
    if lay is None:
        return None
    nl = len(mesh.loops)
    c = np.empty(nl * 4, dtype=np.float32)
    lay.data.foreach_get("color", c)
    c = c.reshape(nl, 4)[:, :3]
    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    totals = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    out = np.empty((len(mesh.polygons), 3), dtype=np.float32)
    for i, (s, t) in enumerate(zip(starts, totals)):
        out[i] = c[s:s + t].mean(axis=0)
    return out


def islands_of(mesh, start_deg=60.0):
    """島を検出して、面ごとのラベルと辺の両側の面を返す。

    最初は STEP0 が焼いた mecha_color から島を復元しようとしたが、
    2.8 のぼかし処理で色が面の中でばらついており(実測: 面内の振れ
    中央 0.49)、色からは復元できなかった。島検出を直接呼ぶ。
    """
    from freepencil2 import mesh_islands as mi
    topo = mi.MeshTopology(mesh)
    used, tries, ratio = mi.resolve_threshold(topo, start_deg, True, True)
    lab = topo.labels
    # 辺の両側の面。-1 はメッシュの縁
    return lab, len(topo.islands), topo.face_a, topo.face_b, used


def _relax_distance(ea, eb, w, nv, src, iters=4000):
    """境界から内側への測地距離。numpy の反復緩和で解く。

    scipy が使えないので Dijkstra ではなく Bellman-Ford 風に回す。
    値が動かなくなったら止める。
    """
    INF = np.float64(1e30)
    d = np.full(nv, INF)
    d[src] = 0.0
    for _ in range(iters):
        cand_b = d[ea] + w
        cand_a = d[eb] + w
        prev = d
        d = d.copy()
        np.minimum.at(d, eb, cand_b)
        np.minimum.at(d, ea, cand_a)
        if np.array_equal(d, prev):
            break
    d[d >= INF] = 0.0
    return d


def _flood_max(ea, eb, d, nv, iters=4000):
    """奥から手前へ最大の深さを流す。

    各境界頂点は、自分が受け持つ谷の一番深いところの値を受け取る。
    これがその場所の形の太さ(内接円の半径)にあたる。
    """
    m = d.copy()
    for _ in range(iters):
        prev = m
        m = m.copy()
        # 深い側から浅い側へだけ流す
        down = d[ea] > d[eb]
        np.maximum.at(m, eb[down], m[ea[down]])
        up = d[eb] > d[ea]
        np.maximum.at(m, ea[up], m[eb[up]])
        if np.array_equal(m, prev):
            break
    return m


def thickness_field(mesh, lab, fa, fb):
    """境界の頂点に『自分が担当した深さ』を持ち帰らせる。"""
    nv = len(mesh.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)
    ne = len(mesh.edges)
    ev = np.empty(ne * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(ne, 2)
    w = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)

    # 島の境目にある辺 = 両側の面のラベルが違う辺、または片面しかない辺
    two = (fa >= 0) & (fb >= 0)
    cut = np.ones(ne, dtype=bool)
    cut[two] = lab[fa[two]] != lab[fb[two]]
    is_bnd = np.zeros(nv, dtype=bool)
    is_bnd[ev[cut, 0]] = True
    is_bnd[ev[cut, 1]] = True

    src = np.where(is_bnd)[0]
    if src.size == 0:
        return np.zeros(nv), is_bnd
    # 距離は島をまたがせない。境目の辺を外して伸ばす
    keep = ~cut
    d = _relax_distance(ev[keep, 0], ev[keep, 1], w[keep], nv, src)
    m = _flood_max(ev[keep, 0], ev[keep, 1], d, nv)
    return m, is_bnd


def write_attr(obj, values, is_bnd):
    """境界の頂点に太さを、それ以外にも一番近い境界の値を配る。"""
    me = obj.data
    v = values.copy()
    hi = float(np.percentile(v[v > 0], 95)) if (v > 0).any() else 1.0
    v = np.clip(v / max(hi, 1e-9), 0.0, 1.0)
    lay = me.color_attributes.get(ATTR)
    if lay is None:
        lay = me.color_attributes.new(name=ATTR, type="FLOAT_COLOR",
                                      domain="CORNER")
    nl = len(me.loops)
    vi = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("vertex_index", vi)
    c = np.empty((nl, 4), dtype=np.float32)
    c[:, 0] = c[:, 1] = c[:, 2] = v[vi]
    c[:, 3] = 1.0
    lay.data.foreach_set("color", c.ravel())
    me.update()


def attr_material():
    mat = bpy.data.materials.new("FP_Thick")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = ATTR
    em = nt.nodes.new("ShaderNodeEmission")
    ou = nt.nodes.new("ShaderNodeOutputMaterial")
    ou.location = (240, 0)
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
    return mat


def main() -> None:
    fp_batch.install_addon()
    blend = dm.find_blend(MODEL)
    if blend is None:
        raise SystemExit(f"見つからない: {MODEL}")
    meshes, _ = dm.load(blend)
    dm.grey(meshes)
    dm.stage(meshes)

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
    say(f"STEP0 {time.time() - t:.1f}秒")

    stats = []
    for o in meshes:
        if o.hide_render:
            continue
        me = o.data
        t = time.time()
        lab, n, fa, fb, used = islands_of(me)
        thick, is_bnd = thickness_field(me, lab, fa, fb)
        write_attr(o, thick, is_bnd)
        tb = thick[is_bnd]
        stats.append({"obj": o.name, "faces": len(me.polygons), "islands": n,
                      "bnd_verts": int(is_bnd.sum()),
                      "thick_med": round(float(np.median(tb)), 5) if tb.size else 0,
                      "thick_p95": round(float(np.percentile(tb, 95)), 5) if tb.size else 0,
                      "sec": round(time.time() - t, 1)})
        say(f"{o.name}: 島 {n} ({used:.0f}度)  境界頂点 {int(is_bnd.sum())}  "
            f"太さ 中央{stats[-1]['thick_med']} 95%{stats[-1]['thick_p95']}  "
            f"{stats[-1]['sec']}秒")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    sc.use_nodes = True
    fp_batch.render_still(sc, OUT / "line.png", 1)
    sc.use_nodes = False
    sc.fp_white_preview = False
    fp_batch.render_still(sc, OUT / "plain.png", 1)

    saved = {o.name: [s.material for s in o.material_slots] for o in meshes}
    pmat = attr_material()
    keep = sc.view_settings.view_transform
    sc.view_settings.view_transform = "Standard"
    for o in meshes:
        for s in o.material_slots:
            s.material = pmat
    fp_batch.render_still(sc, OUT / "thick.png", 1)
    sc.view_settings.view_transform = keep
    for o in meshes:
        for s, m in zip(o.material_slots, saved[o.name]):
            s.material = m

    (OUT / "arc.json").write_text(json.dumps(
        {"model": MODEL, "res": [RES_W, RES_H], "stats": stats},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
