"""法線の塗りを「ゆるく」する。深度と法線の中間を探る。

法線をそのまま色にすると、細かい凹凸まで全部ひろってしまう。線を
大きな形の変わり目だけに絞りたい。方向は2つある。

  soft  法線を頂点どうしで**均す**。均す距離を物体サイズの割合で
        決めるので、面の細かさによらず「同じ距離ぶん」ゆるくなる。
        小さい凹凸は消え、大きな面の向きだけが残る
  pos   オブジェクト空間の**位置**を色に混ぜる。位置は法線と違って
        向きではなく場所で決まるので、深度に近い。混ぜると
        「向きは同じだが離れている」所にも色差が生まれる

    col = (1-w) * (均した法線 * 0.5 + 0.5) + w * 正規化した位置

w=0 が純粋な法線、w=1 が純粋な位置(=物体空間の深度3軸)。その間を見る。

判定は画像で行う(CLAUDE.md)。

    blender -b --factory-startup --python eval_normal_soft.py -- \
        [--softs 0,0.03,0.06,0.12] [--ws 0,0.3]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "normal_soft"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
LEVELS = int(arg("--levels", "2"))
ZOOM = float(arg("--zoom", "1.7"))
SOFTS = [float(x) for x in arg("--softs", "0,0.03,0.06,0.12").split(",")]
WS = [float(x) for x in arg("--ws", "0,0.3").split(",")]
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def suzanne(applied):
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("Sub", type="SUBSURF")
    m.levels = m.render_levels = LEVELS
    if applied:
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o


SHAPES = [("スザンヌ(適用済み)", lambda: suzanne(True)),
          ("スザンヌ(ケージ)", lambda: suzanne(False))]


def mesh_arrays(mesh):
    nv = len(mesh.vertices)
    co = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    vn = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("normal", vn)
    vn = vn.reshape(-1, 3).astype(np.float64)
    ev = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    return co, vn, ev


def soft_rounds(co, ev, dist_frac):
    """均す回数を「物体サイズに対する距離」から出す。

    拡散が届く距離は およそ sqrt(回数) x 辺長 なので、
    回数 = (目標距離 / 辺長)^2 なら面の細かさによらず同じ距離になる
    (回数固定にするとケージだけ潰れる。実測済み)。
    """
    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    el = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    mean_edge = float(np.mean(el)) if len(el) else size
    return int(round((size * dist_frac / max(mean_edge, 1e-9)) ** 2)), size


def smooth_vecs(vec, ev, nv, iters):
    """頂点の値を辺づたいに平均する。"""
    if iters <= 0:
        return vec
    a, b = ev[:, 0].astype(np.int64), ev[:, 1].astype(np.int64)
    deg = np.bincount(np.concatenate([a, b]), minlength=nv).astype(np.float64)
    deg[deg == 0] = 1.0
    v = vec.copy()
    for _ in range(iters):
        acc = v.copy()
        np.add.at(acc, a, v[b])
        np.add.at(acc, b, v[a])
        v = acc / (deg + 1.0)[:, None]
    return v


def paint(obj, dist_frac, w):
    mesh = obj.data
    co, vn, ev = mesh_arrays(mesh)
    nv = len(mesh.vertices)
    rounds, size = soft_rounds(co, ev, dist_frac)
    n = smooth_vecs(vn, ev, nv, rounds)
    ln = np.linalg.norm(n, axis=1)
    ln[ln < 1e-12] = 1.0
    n /= ln[:, None]

    ncol = n * 0.5 + 0.5
    pcol = (co - co.min(axis=0)) / max(size, 1e-9)
    col = (1.0 - w) * ncol + w * pcol

    lv = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    cc = col[lv].astype(np.float32)
    attr = mesh.color_attributes.get("mecha_color")
    if attr is None:
        attr = mesh.color_attributes.new(name="mecha_color", type='BYTE_COLOR',
                                         domain='CORNER')
    buf = np.ones(len(mesh.loops) * 4, dtype=np.float32)
    buf[0::4] = cc[:, 0]
    buf[1::4] = cc[:, 1]
    buf[2::4] = cc[:, 2]
    attr.data.foreach_set("color", buf)
    mesh.color_attributes.active_color = attr
    return rounds


def look(o, zoom):
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    pts = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    ctr = (mn + mx) * 0.5
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 1e-4)
    cd = bpy.data.cameras.new("C")
    cd.lens = 50.0
    cd.clip_end = size * 40
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    d = Vector((0.30, -1.0, 0.14)).normalized()
    cam.location = ctr + d * (size * zoom)
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.lights.new("L", type="AREA")
    lt.energy = size * size * 900.0
    lt.size = size * 2.0
    lo = bpy.data.objects.new("L", lt)
    sc.collection.objects.link(lo)
    lo.location = ctr + Vector((0.4, -0.8, 1.4)) * size


def render_vc(sc, o, png):
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
    keep = [s.material for s in o.material_slots]
    for s in o.material_slots:
        s.material = mat
    kc, kv = sc.use_nodes, sc.view_settings.view_transform
    sc.use_nodes = False
    sc.view_settings.view_transform = 'Standard'
    fp_batch.render_still(sc, png, 1)
    sc.use_nodes, sc.view_settings.view_transform = kc, kv
    for s, m2 in zip(o.material_slots, keep):
        s.material = m2


def one(tag, make, dist_frac, w):
    from freepencil2 import fp_core
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    o = make()
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_preview_mode = 'NONE'
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.shade_smooth()
    rounds = paint(o, dist_frac, w)

    if not o.material_slots:
        o.data.materials.append(bpy.data.materials.new("FP_Mat"))
    for s in o.material_slots:
        if s.material is None:
            s.material = bpy.data.materials.new("FP_Mat")
        s.material.use_nodes = True
    fp_core.setup_aov(sc, bpy.context.view_layer)
    fp_core.setup_compositor(sc, bpy.context.view_layer)

    look(o, ZOOM)
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    key = f"{tag}_s{dist_frac * 100:.0f}w{w * 100:.0f}"
    fp_batch.render_still(sc, OUT / f"{key}_line.png", 1)
    render_vc(sc, o, OUT / f"{key}_vc.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    say(f"{key}: 面{len(o.data.polygons):,} ゆるさ{dist_frac} "
        f"(均し{rounds}回) 位置混ぜ{w}")
    return {"key": key, "soft": dist_frac, "w": w, "rounds": rounds}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"n{i:02d}"
        for s in SOFTS:
            for w in WS:
                try:
                    r = one(tag, make, s, w)
                    r["label"] = label
                    rows.append(r)
                except Exception as e:                   # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    say(f"{tag}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"levels": LEVELS, "rows": rows}, ensure_ascii=False,
                   indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
