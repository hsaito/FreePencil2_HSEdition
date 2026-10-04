"""法線の「大きな向き」を引き算して、残りだけを一定角度ぶんの色にする。

凸面が黒く潰れるのは、丸い張り出しそのものが色を大きく動かすから。
なら**その丸みを引いてしまえばいい**。

  m = 法線を距離 R ぶん均したもの   … その場所の「大きな向き」
  d = n - m                        … 大きな向きからのズレだけ

d を色にすれば、なめらかな凸面は n ≒ m なので色が動かない。稜線だけが
ズレを持つので、そこだけ色が変わる。

色の当て方を2通り試す。角度 θ ぶんズレたところで色が振り切る。

  clamp  θ を超えたら**同じ色のまま**(飽和)。ゆるいグラデ1回ぶん
  wrap   θ ごとに**同じ色へ戻る**(三角波)。等高線のように何本も出る

θ=45度くらい、という提案をそのまま真ん中に置いて前後を見る。

判定は画像で行う(CLAUDE.md)。

    blender -b --factory-startup --python eval_normal_hp.py -- \
        [--rs 0.06,0.12] [--thetas 20,45,90] [--ws 0,0.3]
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


OUT = Path(arg("--out", str(HERE / "out" / "normal_hp"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
LEVELS = int(arg("--levels", "2"))
ZOOM = float(arg("--zoom", "1.7"))
RS = [float(x) for x in arg("--rs", "0.06,0.12").split(",")]
THETAS = [float(x) for x in arg("--thetas", "20,45,90").split(",")]
WS = [float(x) for x in arg("--ws", "0,0.3").split(",")]
MODES = arg("--modes", "clamp,wrap").split(",")
# 全体の濃さ。θ を上げても chord(180)=2 で頭打ちなので、そこから先の
# 薄さはここで作る(実測: θ 90 -> 180 で 1.41倍しか薄くならない)
GAINS = [float(x) for x in arg("--gains", "1").split(",")]
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
    """均す回数は距離から。回数固定だと粗いメッシュだけ潰れる(実測)。"""
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
    den = deg + 1.0
    for _ in range(iters):
        acc = v.copy()
        np.add.at(acc, a, v[b])
        np.add.at(acc, b, v[a])
        v = acc / (den if v.ndim == 1 else den[:, None])
    return v


def tri(x):
    """周期2・振幅1の三角波。角がなめらかに折り返すので段差が出ない。"""
    return 2.0 / np.pi * np.arcsin(np.sin(np.pi * x))


def paint(obj, r_frac, theta_deg, w, mode, gain=1.0):
    mesh = obj.data
    co, vn, ev = mesh_arrays(mesh)
    nv = len(mesh.vertices)
    rounds, size = rounds_for(co, ev, r_frac)
    m = diffuse(vn, ev, nv, rounds)
    ln = np.linalg.norm(m, axis=1)
    ln[ln < 1e-12] = 1.0
    m /= ln[:, None]

    d = vn - m
    # 単位ベクトルが θ ずれたときの弦の長さ。これで割ると θ で ±1 になる
    chord = 2.0 * np.sin(np.radians(theta_deg) * 0.5)
    t = d / max(chord, 1e-6)
    t = np.clip(t, -1.0, 1.0) if mode == "clamp" else tri(t)

    ncol = 0.5 + 0.5 * gain * t
    pcol = (co - co.min(axis=0)) / max(size, 1e-9)
    col = np.clip((1.0 - w) * ncol + w * pcol, 0.0, 1.0)

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
    # ズレの大きさの分布(どのくらい飽和しているか)
    dev = np.degrees(2.0 * np.arcsin(np.clip(
        np.linalg.norm(d, axis=1) * 0.5, 0.0, 1.0)))
    return rounds, float(np.median(dev)), float(np.percentile(dev, 99))


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


def one(tag, make, key, r_frac, theta, w, mode, gain=1.0):
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
    rounds, dev50, dev99 = paint(o, r_frac, theta, w, mode, gain)

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
        f"ズレ中央{dev50:.1f}度 上位1%{dev99:.1f}度")
    return {"key": full, "r": r_frac, "theta": theta, "w": w, "mode": mode,
            "rounds": rounds, "dev50": dev50, "dev99": dev99}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"h{i:02d}"
        for mode in MODES:
            for r in RS:
                for th in THETAS:
                    for w in WS:
                      for gn in GAINS:
                        key = (f"{mode}_r{r * 100:.0f}"
                               f"t{th:.0f}w{w * 100:.0f}g{gn * 100:.0f}")
                        try:
                            rr = one(tag, make, key, r, th, w, mode, gn)
                            rr["label"] = label
                            rows.append(rr)
                        except Exception as e:           # noqa: BLE001
                            import traceback
                            traceback.print_exc()
                            say(f"{tag}_{key}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
