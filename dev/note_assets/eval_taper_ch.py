"""入り抜きの実験・第2段。チャンネルを分けて撮る。

第1段で分かったこと:
  ・有機物(スザンヌ)では曲率マスクが入り抜きになった
  ・メカ(発電機)では輪郭線まで消えて破綻した
    平らな面を走る継ぎ目も、面が背を向ける輪郭も、曲率が低いため

仮説: 輪郭(深度チャンネル)は触らず、塗り分け(メカチャンネル)にだけ
入り抜きをかければ、メカでも破綻しないのではないか。

チャンネルごとに線を撮り分けて出す。合成は eval_taper_ch_mix.py。

    ch_depth.png   深度だけ (輪郭・重なり)
    ch_mecha.png   メカだけ (塗り分けの境目)
    ch_all.png     全部 (比較用)
    point.png      凸の尖り
    conc.png       凹の尖り

  blender -b --factory-startup --python eval_taper_ch.py -- \
      --out <dir> [--model suzanne|<pattern>] [--res 1400] [--subdiv 2]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "taper_ch"))).resolve()
RES_W = int(arg("--res", "1400"))
SS = int(arg("--ss", "2"))
MODEL = arg("--model", "suzanne")
SUBDIV = int(arg("--subdiv", "2"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W),
            "--ss", str(SS)]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
import eval_taper as et           # noqa: E402  (尖り具合の計算を借りる)

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()

CHANNELS = ["fp_ch_mecha", "fp_ch_depth", "fp_ch_bone", "fp_ch_gen",
            "fp_ch_mat"]


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def only(scene, keep: str | None) -> None:
    """keep で指定したチャンネルだけ 1.0、他は 0 にする。"""
    for name in CHANNELS:
        if hasattr(scene, name):
            setattr(scene, name, 1.0 if (keep is None or name == keep) else 0.0)


def main() -> None:
    fp_batch.install_addon()
    if MODEL == "suzanne":
        et.SUBDIV = SUBDIV
        meshes = et.build_suzanne()
    else:
        blend = dm.find_blend(MODEL)
        if blend is None:
            raise SystemExit(f"見つからない: {MODEL}")
        meshes, _ = dm.load(blend)
    dm.grey(meshes)
    dm.stage(meshes)

    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    say(f"STEP0 {time.time() - t:.1f}秒")
    say("チャンネル: " + ", ".join(
        f"{n}={getattr(sc, n, None)}" for n in CHANNELS))

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W * SS
    sc.render.resolution_y = RES_H * SS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    sc.use_nodes = True

    for keep, name in ((None, "ch_all.png"), ("fp_ch_depth", "ch_depth.png"),
                       ("fp_ch_mecha", "ch_mecha.png")):
        only(sc, keep)
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, OUT / name, SS)
        say(f"  {name}")
    only(sc, None)

    # 尖り具合のマスク。線と同じ画角で撮る
    saved = {o.name: [s.material for s in o.material_slots] for o in meshes}
    pmat = et.attr_material()
    sc.use_nodes = False
    keep_vt = sc.view_settings.view_transform
    sc.view_settings.view_transform = "Standard"
    for sign, name in ((True, "point.png"), (False, "conc.png")):
        for o in meshes:
            et.write_attr(o, et.pointiness(o.data), sign)
            for s in o.material_slots:
                s.material = pmat
        fp_batch.render_still(sc, OUT / name, SS)
        say(f"  {name}")
    sc.view_settings.view_transform = keep_vt
    for o in meshes:
        for s, m in zip(o.material_slots, saved[o.name]):
            s.material = m

    (OUT / "taper_ch.json").write_text(json.dumps(
        {"model": MODEL, "res": [RES_W, RES_H]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
