"""手描き背景の線の量を 3 案で比べる(低解像度の静止画だけ)。

  precise  仕上がり「精密」(参考)
  cur      手描き背景の今の既定(細い線 0.35。1 回目の塗りは下限 5・稜線 0.45)
  ab       細い線の 1 回目を本当の精密(稜線 0.25)にして、濃さ 0.6
  abc      ab に加えて、奥ほど線を減らす 3.0 -> 2.0

  blender -b --factory-startup --python eval_density_options.py -- \
      [--only japan-apartment,bridge] [--res 800] [--town] [--frames 60,300,600]

--town を付けると町(out/town_v2/town.blend)の 3 フレームを 960x540 で撮る。
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "density_options"))).resolve()
ONLY = arg("--only", "japan-apartment,modern-house,bridge_1K,arched_hangar,"
                     "european-maple,jnr-c62")
RES = int(arg("--res", "800"))
TOWN = "--town" in ARGV
FRAMES = [int(v) for v in arg("--frames", "60,300,600").split(",") if v]
FINE_AB = float(arg("--fine", "0.6"))
SENS_C = float(arg("--sens", "2.0"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)


def repaint_fine_precise(sc, targets):
    """fine_color を本当の精密(下限 5・稜線 0.25)で塗り直し、手描きに戻す。"""
    import importlib
    utils = importlib.import_module(fp_batch.ADDON_NAME + ".utils")
    bpy.ops.object.select_all(action="DESELECT")
    for o in targets:
        o.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    sc.fp_auto_split_floor = 5.0
    sc.fp_ridge_amount = 0.25
    bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")
    for o in targets:
        utils.copy_vertex_color(o, "mecha_color", "fine_color")
    sc.fp_auto_split_floor = 14.0
    sc.fp_ridge_amount = 0.45
    bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")


def relink(sc):
    bpy.ops.freepencil2.link_button()
    # STEP3 を作り直すとモノクロプレビューが外れる(白プレビューだけ戻す実装)。
    # 比較が陰影の違いにならないよう、プレビューの種類を掛け直す
    import importlib
    importlib.import_module(fp_batch.ADDON_NAME + ".props")._apply_preview_mode(sc)


def shoot(sc, path, before=None):
    if before:
        before()
    fp_batch.render_still(sc, path, 1)
    print(f"@@@ {path.name}", flush=True)


def models():
    import make_demo_movie as dm      # noqa: E402
    import eval_style_all as esa      # noqa: E402
    import scan_models                # noqa: E402
    dm.OUT = OUT
    esa.RES = RES

    def prep(path):
        meshes, _ = dm.load(path)
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
        return sc, meshes

    pats = [x for x in ONLY.split(",") if x]
    found = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
             if any(p in Path(m["path"]).stem for p in pats)]
    for m in found:
        name = Path(m["path"]).stem[:16]
        sc, meshes = prep(m["path"])
        sc.fp_auto_style = 'PRECISE'
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sc.fp_white_preview = True
        shoot(sc, OUT / f"{name}_precise.png")

        sc, meshes = prep(m["path"])
        sc.fp_auto_style = 'BACKGROUND'
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sc.fp_white_preview = True
        shoot(sc, OUT / f"{name}_cur.png")
        targets = [o for o in meshes if o.data.color_attributes.get("fine_color")]
        repaint_fine_precise(sc, targets)
        sc.fp_fine_lines = FINE_AB
        relink(sc)
        sc.fp_white_preview = True
        shoot(sc, OUT / f"{name}_ab.png")
        sc.fp_lw_far_sens = SENS_C
        relink(sc)
        sc.fp_white_preview = True
        shoot(sc, OUT / f"{name}_abc.png")


def town():
    sys.argv = ["blender", "--"]
    import shoot_town_v2 as st        # noqa: E402
    bpy.ops.wm.open_mainfile(filepath=str(HERE / "out" / "town_v2" / "town.blend"))
    sc = bpy.context.scene
    cam = sc.camera
    sc.render.resolution_x = 960
    sc.render.resolution_y = 540
    sc.eevee.taa_render_samples = 4
    st.FRAMES = 720
    st.moving_cars(sc)

    def at(f):
        return lambda: (st.aim(cam, f), sc.frame_set(f + 1))

    for f in FRAMES:
        shoot(sc, OUT / f"town{f:04d}_cur.png", at(f))
    targets = [o for o in sc.objects if o.type == "MESH"
               and o.data.color_attributes.get("fine_color")]
    print(f"@@@ 町: fine_color を持つ {len(targets)} 個を塗り直す", flush=True)
    repaint_fine_precise(sc, targets)
    sc.fp_fine_lines = FINE_AB
    relink(sc)
    for f in FRAMES:
        shoot(sc, OUT / f"town{f:04d}_ab.png", at(f))
    sc.fp_lw_far_sens = SENS_C
    relink(sc)
    for f in FRAMES:
        shoot(sc, OUT / f"town{f:04d}_abc.png", at(f))


def main():
    fp_batch.install_addon()
    town() if TOWN else models()
    print(f"@@@ 完了 {OUT}", flush=True)


if __name__ == "__main__":
    main()
