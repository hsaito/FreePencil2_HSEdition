"""島の塗り分け(パーツ+鋭角)に、法線の稜線を**薄く**足して混ぜる。

どちらか一方に倒すと片方が死ぬ。

  島だけ   パーツの区別と鋭角は出るが、なめらかな出っ張りは出ない
  法線だけ なめらかな稜線は出るが、パーツの区別が消える
           (別パーツでも向きが同じなら同じ色になる)

ハイポリのメカは両方要る。だから足す。

    col = 島の色 + amp * (法線 - 均した法線)

島の色は面ごとに一定の値なので、足した残差は**島の中だけを**ゆるく
揺らす。島の境界は元の段差がそのまま残るので、パーツ線は死なない。

amp は小さく保つ。隣接島の色距離の契約(既定 0.5)を割ってはいけない。
最悪ケースで距離が 2*amp だけ縮むので、その分を残す。

島の塗りは実機の STEP1 をそのまま通す(自前で作り直さない)。

    blender -b --factory-startup --python eval_blend.py -- [--amps 0.06,0.12,0.2]
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


OUT = Path(arg("--out", str(HERE / "out" / "blend"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
LEVELS = int(arg("--levels", "2"))
ZOOM = float(arg("--zoom", "1.7"))
RFRAC = float(arg("--r", "0.04"))
AMPS = [float(x) for x in arg("--amps", "0.06,0.12,0.2").split(",")]
# 島を広くまとめる閾値。STEP0 の「おすすめ」は 0.02 なので明示する
PCT = float(arg("--pct", "0.0"))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# ------------------------------------------------------------------ 形
def suzanne(applied):
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("Sub", type="SUBSURF")
    m.levels = m.render_levels = LEVELS
    if applied:
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o


def mecha_hipoly():
    """角を落として細分した硬い形。ハイポリのメカに近い条件を作る。

    箱と円柱を寄せ集めて1つのメッシュにし、ベベル+サブディビを焼く。
    面は細かいが、稜線ははっきりある。
    """
    parts = []
    specs = [("cube", (0, 0, 0), (1.2, 0.8, 0.5)),
             ("cube", (1.6, 0, 0.2), (0.5, 0.5, 0.9)),
             ("cube", (-1.5, 0.1, 0.3), (0.6, 0.7, 0.4)),
             ("cyl", (0.2, 0.0, 1.0), (0.35, 0.35, 0.7)),
             ("cyl", (-0.9, -0.6, -0.6), (0.25, 0.25, 0.9))]
    for kind, loc, sc in specs:
        if kind == "cube":
            bpy.ops.mesh.primitive_cube_add(location=loc)
        else:
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, location=loc)
        o = bpy.context.object
        o.scale = sc
        parts.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.join()
    o = bpy.context.object
    b = o.modifiers.new("B", type="BEVEL")
    b.width = 0.06
    b.segments = 3
    s = o.modifiers.new("S", type="SUBSURF")
    s.levels = s.render_levels = 1
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=b.name)
    bpy.ops.object.modifier_apply(modifier=s.name)
    return o


SHAPES = [("スザンヌ(適用済み)", lambda: suzanne(True)),
          ("スザンヌ(ケージ)", lambda: suzanne(False)),
          ("メカ(ハイポリ)", mecha_hipoly)]


# ---------------------------------------------------------------- 残差
def residual(mesh, r_frac):
    """法線から「大きな向き」を引いた残り。角ごとに返す。"""
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

    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    el = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    mean_edge = float(np.mean(el)) if len(el) else size
    # 均す回数は距離から(回数固定だと粗いメッシュだけ潰れる。実測済み)
    iters = int(round((size * r_frac / max(mean_edge, 1e-9)) ** 2))

    a, b = ev[:, 0].astype(np.int64), ev[:, 1].astype(np.int64)
    deg = np.bincount(np.concatenate([a, b]), minlength=nv).astype(np.float64)
    deg[deg == 0] = 1.0
    m = vn.copy()
    for _ in range(iters):
        acc = m.copy()
        np.add.at(acc, a, m[b])
        np.add.at(acc, b, m[a])
        m = acc / (deg + 1.0)[:, None]
    ln = np.linalg.norm(m, axis=1)
    ln[ln < 1e-12] = 1.0
    m /= ln[:, None]

    d = np.clip((vn - m) * 0.5, -1.0, 1.0)      # 180度ズレで ±1
    lv = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    return d[lv], iters


def blend_into_mecha_color(obj, amp, r_frac):
    """STEP1 が塗った mecha_color に残差を足す。距離の契約は測って報告する。"""
    mesh = obj.data
    attr = mesh.color_attributes.get("mecha_color")
    if attr is None:
        return None
    nl = len(mesh.loops)
    buf = np.empty(nl * 4, dtype=np.float32)
    attr.data.foreach_get("color", buf)
    base = buf.reshape(-1, 4)[:, :3].astype(np.float64)
    d, iters = residual(mesh, r_frac)
    out = np.clip(base + amp * d, 0.0, 1.0)
    buf2 = buf.reshape(-1, 4).copy()
    buf2[:, :3] = out
    attr.data.foreach_set("color", buf2.ravel())
    mesh.color_attributes.active_color = attr
    # 島の色そのものは何色あったか(足す前)を数えておく
    uniq = np.unique(np.round(base, 4), axis=0)
    return iters, len(uniq), float(np.abs(amp * d).max())


# ------------------------------------------------------------------ 撮影
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


def one(tag, make, key, amp):
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
    sc.fp_auto_sharp = False
    sc.fp_sharp_auto = True
    sc.fp_curve_blur = 0
    sc.fp_auto_merge = False
    sc.fp_min_island_area_pct = PCT

    # 島の塗りは実機の STEP1 をそのまま使う
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    note = "島のみ"
    if amp > 0.0:
        r = blend_into_mecha_color(o, amp, RFRAC)
        if r:
            note = f"島{r[1]}色 + 残差{amp}(最大ズレ{r[2]:.3f}, 均し{r[0]}回)"

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
    say(f"{full}: 面{len(o.data.polygons):,}  {note}")
    return {"key": full, "amp": amp}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"c{i:02d}"
        for amp in [0.0] + AMPS:
            key = f"a{amp * 100:.0f}"
            try:
                r = one(tag, make, key, amp)
                r["label"] = label
                rows.append(r)
            except Exception as e:                       # noqa: BLE001
                import traceback
                traceback.print_exc()
                say(f"{tag}_{key}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"r": RFRAC, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
