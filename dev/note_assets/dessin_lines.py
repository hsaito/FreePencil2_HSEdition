"""デッサン人形(社内の .blend のローカルコピー)で線を出す。

共有ドライブには書かない。コピーしたファイルを開き、カメラとライトを
足して、仕上がりごとに STEP0 -> 1枚レンダ。塗り分けも素通しで撮る。

  blender -b --factory-startup --python dessin_lines.py -- \
      [--src out/dessin/dessin170_src.blend] [--styles WEIGHTED,PRECISE] [--res 960]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
SRC = Path(arg("--src", str(HERE / "out" / "dessin" / "dessin170_src.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "dessin"))).resolve()
STYLES = arg("--styles", "WEIGHTED,PRECISE").split(",")
RES = int(arg("--res", "960"))
SAMPLES = int(arg("--samples", "8"))

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

KEY = {"PRECISE": "precise", "WEIGHTED": "char", "BACKGROUND": "bg"}


def meshes_of(sc):
    return [o for o in sc.objects if o.type == "MESH" and not o.hide_render
            and len(o.data.polygons) > 0]


def stage(sc, meshes):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (lo + hi) / 2
    h = max(hi.z - lo.z, 0.1)
    cd = bpy.data.cameras.new("C")
    cd.lens = 50.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    d = h * 2.6
    a = math.radians(25.0)
    cam.location = (ctr.x + math.sin(a) * d, ctr.y - math.cos(a) * d, ctr.z + h * 0.12)
    cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.objects.new("K", bpy.data.lights.new("K", type="SUN"))
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(50), 0, math.radians(-35))
    print(f"@@@ 高さ {h:.2f} 中心 {tuple(round(v, 2) for v in ctr)}", flush=True)


def vcol_still(sc, meshes, path, attr):
    m = bpy.data.materials.new("look_" + attr)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = "GEOMETRY"
    a.attribute_name = attr
    e = nt.nodes.new("ShaderNodeEmission")
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(a.outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
    saved = [(ms, ms.link, ms.material) for ob in meshes for ms in ob.material_slots]
    for ob in meshes:
        for ms in ob.material_slots:
            ms.link = "OBJECT"
            ms.material = m
    comp, pct, ft = (sc.render.use_compositing, sc.render.resolution_percentage,
                     sc.render.film_transparent)
    sc.render.use_compositing = False
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    sc.render.use_compositing, sc.render.resolution_percentage = comp, pct
    sc.render.film_transparent = ft
    for ms, link, mat in saved:
        ms.link = link
        ms.material = mat


def open_scene():
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    sc = bpy.context.scene
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = SAMPLES
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    meshes = meshes_of(sc)
    if "--apply-mirror" in ARGV:               # 左右を別の塗りにできるよう、ミラーを実体にする
        for o in meshes:
            md = next((m for m in o.modifiers if m.type == "MIRROR"), None)
            if md is None:
                continue
            bpy.ops.object.select_all(action="DESELECT")
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            if o.data.shape_keys:
                # シェイプキーがあると適用できないので、基底に焼いて外す
                o.shape_key_clear()
            bpy.ops.object.modifier_apply(modifier=md.name)
    if "--walk" in ARGV:                       # 歩きの途中のポーズ(脚が開いたところ)
        import dessin_walk
        dessin_walk.make_walk(bpy.data.objects["man_rig"])
        sc.frame_set(int(arg("--walk", "7")) if arg("--walk", "7").isdigit() else 7)
    stage(sc, meshes)
    return sc, meshes


def main():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    # 素の見た目(比較用)
    sc, meshes = open_scene()
    sc.render.filepath = str(OUT / "plain.png")
    bpy.ops.render.render(write_still=True)
    for style in STYLES:
        sc, meshes = open_scene()
        for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
                   "fp_auto_detect_aov", "fp_auto_white_preview"):
            setattr(sc, p_, False)
        sc.fp_color_seed = 42
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        sc.fp_auto_style = style
        if "--fine-rig-precise" in ARGV:
            sc["fp_fine_rig_precise"] = True
        if "--side-tone" in ARGV:
            sc["fp_bone_side_tone"] = True
        if arg("--bone-smooth") is not None:   # ボーンの色をぼかす回数(実験)
            sc["fp_bone_smooth"] = int(arg("--bone-smooth"))
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sc.fp_white_preview = True
        if "--mono" in ARGV:
            sc.fp_mono_floor = 0.55
            sc.fp_preview_mode = 'MONO_LIGHT'
        k = KEY[style]
        fp_batch.render_still(sc, OUT / f"{k}.png", 1)
        vcol_still(sc, meshes, OUT / f"{k}_mecha.png", "mecha_color")
        vcol_still(sc, meshes, OUT / f"{k}_bone.png", "bone_color")
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"dessin170_{k}.blend"))
        print(f"@@@ {style} done bone_aov={sc.fp_bone_color}", flush=True)


if __name__ == "__main__":
    main()
