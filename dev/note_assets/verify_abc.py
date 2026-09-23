"""案 ABC を既定値に入れたあと、本物の STEP0 で撮り直して比べる。

  models : 精密 と 手描き背景 を STEP0 そのままで撮る(eval_density_options の
           precise / abc と同じ条件)
  --town : 町の 300 フレームを、STEP3 を作り直してから撮る(モノクロが
           外れないこと。5.x でも陰影が出ること)

  blender -b --factory-startup --python verify_abc.py -- [--town] [--tag 452]
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "verify_abc"))).resolve()
ONLY = arg("--only", "japan-apartment,jnr-c62,european-maple")
TAG = arg("--tag", "")
RES = 800
TOWN = "--town" in ARGV

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)


def models():
    import make_demo_movie as dm      # noqa: E402
    import eval_style_all as esa      # noqa: E402
    import scan_models                # noqa: E402
    dm.OUT = OUT
    esa.RES = RES
    found = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
             if any(p in Path(m["path"]).stem for p in ONLY.split(","))]
    for m in found:
        name = Path(m["path"]).stem[:16]
        keys = {'PRECISE': "precise", 'WEIGHTED': "char", 'BACKGROUND': "abc"}
        for style in arg("--styles", "PRECISE,BACKGROUND").split(","):
            key = keys[style]
            meshes, _ = dm.load(m["path"])
            dm.grey(meshes)
            esa.stage(meshes)
            sc = bpy.context.scene
            for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
                       "fp_auto_detect_aov", "fp_auto_white_preview"):
                setattr(sc, p_, False)
            sc.fp_color_seed = 42
            sc.render.engine = fp_batch.eevee_engine()
            sc.eevee.taa_render_samples = 16
            sc.render.resolution_x = sc.render.resolution_y = RES
            sc.render.image_settings.file_format = "PNG"
            sc.render.image_settings.color_mode = "RGBA"
            sc.render.film_transparent = True
            bpy.ops.object.select_all(action="DESELECT")
            for o in meshes:
                o.select_set(True)
            bpy.context.view_layer.objects.active = meshes[0]
            sc.fp_auto_style = style
            if "--bone-islands" in ARGV:      # キャラの塗り分けをボーン基準に(実験)
                sc["fp_bone_islands"] = True
            if arg("--bone-smooth") is not None:   # ボーンの色をぼかす回数(実験)
                sc["fp_bone_smooth"] = int(arg("--bone-smooth"))
            bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
            sc.fp_white_preview = True
            print(f"@@@ {name} {style} fine={sc.fp_fine_lines} sens={sc.fp_lw_far_sens}", flush=True)
            fp_batch.render_still(sc, OUT / f"{name}_{key}.png", 1)
            if "--vcol" in ARGV:
                for attr in arg("--vcol-attrs", "mecha_color").split(","):
                    vcol_still(sc, meshes, OUT / f"{name}_{key}_{attr.split('_')[0]}.png", attr)


def vcol_still(sc, meshes, path, attr="mecha_color"):
    """色属性を Attribute -> Emission で素通しに撮る(塗り分けを見る)。"""
    m = bpy.data.materials.new("look_mecha")
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
    comp, pct = sc.render.use_compositing, sc.render.resolution_percentage
    sc.render.use_compositing = False
    sc.render.resolution_percentage = 100
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    sc.render.use_compositing, sc.render.resolution_percentage = comp, pct
    for ms, link, mat in saved:
        ms.link = link
        ms.material = mat


def town():
    sys.argv = ["blender", "--"]
    import shoot_town_v2 as st        # noqa: E402
    bpy.ops.wm.open_mainfile(filepath=str(HERE / "out" / "town_v2" / "town.blend"))
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.eevee.taa_render_samples = 4
    st.FRAMES = 720
    if bpy.app.version < (5, 0, 0):
        st.moving_cars(sc)         # 5.x はアクションの形が違う(このデモ用の処理だけ)
    bpy.ops.freepencil2.link_button()          # 作り直してもモノクロのまま
    print(f"@@@ town preview={sc.fp_preview_mode}", flush=True)
    st.aim(sc.camera, 300)
    sc.frame_set(301)
    fp_batch.render_still(sc, OUT / f"town0300_relink_{TAG or bpy.app.version_string}.png", 1)


def main():
    fp_batch.install_addon()
    town() if TOWN else models()
    print(f"@@@ 完了 {OUT}", flush=True)


if __name__ == "__main__":
    main()
