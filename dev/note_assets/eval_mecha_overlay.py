"""手描き背景の線に、精密(メカ)の線を薄く重ねられるか試す。

手描き背景は「なめらかな面を割らない(下限14度・稜線0.45)」ので、
窓枠やパネルの細かい線が精密より少ない。精密で撮った線を薄く足せば、
情報量だけ戻せるのではないか、という案。

精密と手描き背景は STEP1 の塗り分けが違う(下限 5度/14度、稜線 0.25/0.45)
ので、同じレンダでは両方出せない。2回撮って合成する。

  blender -b --factory-startup --python eval_mecha_overlay.py -- \
      [--blend out/town_v2/town.blend] [--out out/mecha_overlay] [--frames 60,300,600]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "town_v2" / "town.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "mecha_overlay"))).resolve()
FRAMES = [int(v) for v in arg("--frames", "60,300,600").split(",") if v]
RES = int(arg("--res", "1920"))

sys.argv = ["blender", "--"]      # shoot_town_v2 は import 時に自分の引数を読む
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import shoot_town_v2 as shoot      # noqa: E402  (aim / moving_cars と同じ経路)
import bpy                         # noqa: E402
import fp_batch                    # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)


def main():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    cam = sc.camera
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    shoot.FRAMES = 720
    shoot.moving_cars(sc)

    # 1) 手描き背景(今のまま)
    for f in FRAMES:
        shoot.aim(cam, f)
        sc.frame_set(f + 1)
        fp_batch.render_still(sc, OUT / f"f{f:04d}_bg.png", 1)
        print(f"@@@ bg f{f:04d}", flush=True)

    # 2) 精密で塗り直して同じカメラで撮る
    bpy.ops.object.select_all(action="DESELECT")
    targets = [o for o in sc.objects
               if o.type == "MESH" and not o.hide_viewport and o.name != "FP_ground"]
    for o in targets:
        o.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    sc.fp_auto_style = 'PRECISE'
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_ch_depth = 0.0            # 地平線の帯は背景と同じ条件で消す
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = 'MONO_LIGHT'
    bpy.ops.freepencil2.link_button()
    sc.fp_preview_mode = 'MONO_LIGHT'
    print(f"@@@ 精密に塗り直した style={sc.fp_auto_style} 強弱={sc.fp_line_weight}", flush=True)
    for f in FRAMES:
        shoot.aim(cam, f)
        sc.frame_set(f + 1)
        fp_batch.render_still(sc, OUT / f"f{f:04d}_precise.png", 1)
        print(f"@@@ precise f{f:04d}", flush=True)
    print(f"@@@ 完了 {OUT}", flush=True)


if __name__ == "__main__":
    main()
