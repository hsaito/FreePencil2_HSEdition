"""広い範囲を同じ色にする。ただしパーツ同士は必ず違う色にする。

島は鋭角ごとに切れるので、1つのパーツの中が細かく分かれて色が散る。
広い面を1色にしたいなら、**面積の小さい島を隣の大きい島へ併合する**。
これは既にアドオンにある (fp_min_island_area_pct)。効き方を絵で確かめる。

大事なのは併合が**ルースパーツを越えられない**こと。併合先は「辺を
共有する隣の島」なので、辺を共有しないパーツ同士は絶対にくっつかない。
つまり閾値をいくら上げても、パーツは別の島のまま残る。

そのうえで色を分けるのは add_loose_part_proximity(今日入れた近接隣接)。
辺で繋がっていないパーツ同士も「隣」と見なすので、同じ色にならない。

  併合で   -> パーツの中が1色にまとまる
  近接隣接で -> パーツ同士は違う色になる

閾値を振って、どこまで広げられるかを見る。

    blender -b --factory-startup --python eval_wide.py -- [--pcts 0,2,5,10,20]
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


OUT = Path(arg("--out", str(HERE / "out" / "wide"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
LEVELS = int(arg("--levels", "2"))
ZOOM = float(arg("--zoom", "1.7"))
PCTS = [float(x) for x in arg("--pcts", "0,0.5,1,2,5").split(",")]
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


def mecha_hipoly():
    """箱と円柱を寄せ集めて焼いた硬い形。ハイポリのメカに近い条件。"""
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


def loose_cubes():
    """離れた立方体8個を1メッシュに。パーツ分けが効いているかの確認用。"""
    parts = []
    for i, loc in enumerate([(0, 0, 0), (2.2, 0, 0), (0, 2.2, 0),
                             (2.2, 2.2, 0), (0, 0, 2.2), (2.2, 0, 2.2),
                             (0, 2.2, 2.2), (2.2, 2.2, 2.2)]):
        bpy.ops.mesh.primitive_cube_add(size=1.8, location=loc)
        parts.append(bpy.context.object)
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    return bpy.context.object


SHAPES = [("スザンヌ(適用済み)", lambda: suzanne(True)),
          ("メカ(ハイポリ)", mecha_hipoly),
          ("離れた立方体8個", loose_cubes)]


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


def count_colors(o):
    me = o.data
    attr = me.color_attributes.get("mecha_color")
    if attr is None:
        return 0
    buf = np.empty(len(me.loops) * 4, dtype=np.float32)
    attr.data.foreach_get("color", buf)
    return len(np.unique(np.round(buf.reshape(-1, 4)[:, :3], 3), axis=0))


def one(tag, make, pct):
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
    # STEP0 の「おすすめ」が 0.02 で上書きするので切る
    sc.fp_auto_merge = False
    sc.fp_min_island_area_pct = pct

    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    n_col = count_colors(o)

    look(o, ZOOM)
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    key = f"{tag}_p{pct * 10:.0f}"
    fp_batch.render_still(sc, OUT / f"{key}_line.png", 1)
    render_vc(sc, o, OUT / f"{key}_vc.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    say(f"{key}: 面{len(o.data.polygons):,} 併合しきい値{pct}% 実際の色数{n_col}")
    return {"key": key, "pct": pct, "colors": n_col}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"w{i:02d}"
        for pct in PCTS:
            try:
                r = one(tag, make, pct)
                r["label"] = label
                rows.append(r)
            except Exception as e:                       # noqa: BLE001
                import traceback
                traceback.print_exc()
                say(f"{tag} {pct}: 失敗 {e}")
    (OUT / "index.json").write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
