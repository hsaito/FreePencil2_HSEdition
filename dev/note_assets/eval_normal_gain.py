"""法線塗りの「凸面が真っ黒に潰れる」を、色変化の強さを絞って直す。

法線をそのまま色にすると、線が出るかどうかは |法線の変化率| = 曲率 で
決まる。だから丸く張り出した面は**面全体が一様にしきい値を超えて**
インクで埋まる。稜線だけが出てほしいのに、凸面ぜんぶが出てしまう。

色変化を弱めれば、そこそこ曲がっている面はしきい値の下に落ち、
本当に鋭い所だけが残る。2通りで弱める。

  flat   一律に振幅を絞る。   col = 0.5 + gain * (法線 * 0.5)
         gain=1 が従来。gain を下げるほど、ゆるい凸は色が動かなくなる

  adapt  曲がっている所ほど強く絞る。
         gain(v) = 1 / (1 + beta * 曲率の相対値)
         凸面では色がゆっくり変わり、平らな所では従来どおり。
         gain 自体が段になると偽の線が出るので、曲率は先に強く均して
         なだらかにしてから使う

前回の「ゆるさ(法線を均す)」「位置混ぜ(深度寄り)」はそのまま土台にする。

    col = (1-w) * (0.5 + gain * (均した法線 * 0.5)) + w * 正規化した位置

判定は画像で行う(CLAUDE.md)。

    blender -b --factory-startup --python eval_normal_gain.py -- \
        [--soft 0.06] [--w 0.3] [--gains 1,0.6,0.35,0.2] [--betas 1,3,8]
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


OUT = Path(arg("--out", str(HERE / "out" / "normal_gain"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
LEVELS = int(arg("--levels", "2"))
ZOOM = float(arg("--zoom", "1.7"))
SOFT = float(arg("--soft", "0.06"))
WPOS = float(arg("--w", "0.3"))
GAINS = [float(x) for x in arg("--gains", "1,0.6,0.35,0.2").split(",")]
BETAS = [float(x) for x in arg("--betas", "1,3,8").split(",")]
KSMOOTH = float(arg("--ksmooth", "0.12"))   # 曲率を均す距離(サイズ比)
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


def sphere():
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32)
    return bpy.context.object


SHAPES = [("スザンヌ(適用済み)", lambda: suzanne(True)),
          ("スザンヌ(ケージ)", lambda: suzanne(False)),
          ("UV球", sphere)]


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


def rounds_for(co, ev, dist_frac):
    """均す回数を距離から。回数固定だと粗いメッシュだけ潰れる(実測)。"""
    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    el = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    mean_edge = float(np.mean(el)) if len(el) else size
    return int(round((size * dist_frac / max(mean_edge, 1e-9)) ** 2)), size


def diffuse(val, ev, nv, iters):
    if iters <= 0:
        return val
    a, b = ev[:, 0].astype(np.int64), ev[:, 1].astype(np.int64)
    deg = np.bincount(np.concatenate([a, b]), minlength=nv).astype(np.float64)
    deg[deg == 0] = 1.0
    v = val.copy()
    two_d = deg + 1.0
    for _ in range(iters):
        acc = v.copy()
        np.add.at(acc, a, v[b])
        np.add.at(acc, b, v[a])
        v = acc / (two_d if v.ndim == 1 else two_d[:, None])
    return v


def curvature(co, vn, ev, nv, size):
    """頂点ごとの曲がりの速さ。辺長で割ってサイズで無次元化する。"""
    a, b = ev[:, 0].astype(np.int64), ev[:, 1].astype(np.int64)
    ln = np.linalg.norm(co[a] - co[b], axis=1)
    ln[ln < 1e-12] = 1e-12
    dot = np.clip(np.einsum("ij,ij->i", vn[a], vn[b]), -1.0, 1.0)
    k_edge = np.arccos(dot) / ln * size
    acc = np.zeros(nv)
    cnt = np.zeros(nv)
    np.add.at(acc, a, k_edge)
    np.add.at(acc, b, k_edge)
    np.add.at(cnt, a, 1.0)
    np.add.at(cnt, b, 1.0)
    cnt[cnt == 0] = 1.0
    return acc / cnt


def paint(obj, soft, w, gain, beta):
    mesh = obj.data
    co, vn, ev = mesh_arrays(mesh)
    nv = len(mesh.vertices)
    n_rounds, size = rounds_for(co, ev, soft)
    n = diffuse(vn, ev, nv, n_rounds)
    ln = np.linalg.norm(n, axis=1)
    ln[ln < 1e-12] = 1.0
    n /= ln[:, None]

    if beta > 0.0:
        k = curvature(co, vn, ev, nv, size)
        k_rounds, _ = rounds_for(co, ev, KSMOOTH)
        # gain が段になると偽の線が出る。曲率は強く均してなだらかにする
        k = diffuse(k, ev, nv, k_rounds)
        med = float(np.median(k)) or 1.0
        g = 1.0 / (1.0 + beta * (k / med))
        g = g / float(g.max())          # 最大が 1 になるよう正規化
    else:
        g = np.full(nv, gain)

    ncol = 0.5 + g[:, None] * (n * 0.5)
    pcol = (co - co.min(axis=0)) / max(size, 1e-9)
    col = (1.0 - w) * ncol + w * pcol

    lv = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    cc = np.clip(col[lv], 0.0, 1.0).astype(np.float32)
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
    return n_rounds, float(g.min()), float(g.max())


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


def one(tag, make, key, gain, beta):
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
    rounds, gmin, gmax = paint(o, SOFT, WPOS, gain, beta)

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
    full = f"{tag}_{key}"
    fp_batch.render_still(sc, OUT / f"{full}_line.png", 1)
    render_vc(sc, o, OUT / f"{full}_vc.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{full}.blend"))
    say(f"{full}: 面{len(o.data.polygons):,} 均し{rounds}回 "
        f"強さ{gmin:.2f}〜{gmax:.2f}")
    return {"key": full, "gain": gain, "beta": beta, "rounds": rounds}


def main():
    fp_batch.install_addon()
    rows = []
    cases = [(f"g{g * 100:.0f}", g, 0.0) for g in GAINS]
    cases += [(f"b{b:.0f}", 1.0, b) for b in BETAS]
    for i, (label, make) in enumerate(SHAPES):
        tag = f"p{i:02d}"
        for key, g, b in cases:
            try:
                r = one(tag, make, key, g, b)
                r["label"] = label
                rows.append(r)
            except Exception as e:                       # noqa: BLE001
                import traceback
                traceback.print_exc()
                say(f"{tag}_{key}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"soft": SOFT, "w": WPOS, "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
