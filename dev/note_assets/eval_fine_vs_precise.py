"""細い線(fine_color)が、精密モードの線をどれだけ再現できているか測る。

同じモデルで:
    precise      仕上がり「精密」
    bg           仕上がり「手描き背景」細い線 0
    bg_fine1.0   同上で細い線 1.0(いちばん濃く重ねた状態)
を撮り、インク量と、精密との差を見る。

  blender -b --factory-startup --python eval_fine_vs_precise.py -- \
      [--only camera_2K] [--res 1200]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "fine_vs_precise"))).resolve()
ONLY = arg("--only", "camera_2K,lancia-delta,jnr-c62")
RES = int(arg("--res", "1200"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import eval_style_all as esa      # noqa: E402  (stage / measure を使う)
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402

dm.OUT = OUT
esa.RES = RES
OUT.mkdir(parents=True, exist_ok=True)


def prep(path):
    meshes, _ = dm.load(path)
    dm.grey(meshes)
    esa.stage(meshes)
    sc = bpy.context.scene
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.fp_white_preview = True
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


def main():
    fp_batch.install_addon()
    pats = [x for x in ONLY.split(",") if x]
    models = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
              if any(p in Path(m["path"]).stem for p in pats)]
    for m in models:
        name = Path(m["path"]).stem[:20]
        for style, tag in (('PRECISE', "precise"), ('BACKGROUND', "bg")):
            sc, meshes = prep(m["path"])
            sc.fp_auto_style = style
            bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
            sc.fp_white_preview = True
            if style == 'PRECISE':
                fp_batch.render_still(sc, OUT / f"{name}_precise.png", 1)
                print(f"@@@ {name} precise", esa.measure(OUT / f'{name}_precise.png'), flush=True)
            else:
                for k in (0.0, 0.35, 1.0):
                    sc.fp_fine_lines = k
                    bpy.ops.freepencil2.link_button()
                    sc.fp_white_preview = True
                    p = OUT / f"{name}_bg{k:g}.png"
                    fp_batch.render_still(sc, p, 1)
                    print(f"@@@ {name} bg fine={k:g}", esa.measure(p), flush=True)
    print(f"@@@ 完了 {OUT}", flush=True)


if __name__ == "__main__":
    main()
