"""v2.7 の「買う理由になる機能」を主役にしたデモの素材を撮る。

前のデモ (make_demo_movie.py) は「線が出ます」という紹介だった。
こちらは note の読者が 2.5.0 から上がってくることを前提に、
上げると何が良くなるのかだけを見せる。カメラは全ショットで動かす。

  hero   メカを回す。線あり。掴み
  sens   帆船を回す。線の感度 1.0 と 0.5 を同じ回転で2本撮る。
         v2.7 の変更そのもの。索具の点線が実線になる
  speed  なし (実キャプチャの進捗バーを組み立て側で使う)

町のドリー (遠景つぶれ軽減) は make_town_movie.py を --relief 0 と
--relief 0.6 で2回まわす。あちらのシーン作りをそのまま使いたいため。

  blender -b --factory-startup --python make_v27_movie.py -- \
      --out <dir> [--res 1600] [--ss 2] [--frames 96] [--shot sens]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "v27"))).resolve()
RES_W = int(arg("--res", "1600"))
SS = int(arg("--ss", "2"))
FRAMES = int(arg("--frames", "96"))
ONLY = arg("--shot")

# make_demo_movie の読み込み・整形・カメラ・ライトをそのまま使う。
# 同じ絵作りにしておかないと、前のデモと並べたときに揃わない。
# 先に argv を差し替えてから import すること (向こうも -- を読む)
sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W),
            "--ss", str(SS)]
# Blender から --python で走らせると、このファイルの場所は sys.path に
# 入らない。隣のスクリプトを import するので自分で足す
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()

HERO = ("mech", "kaino-school-military-mech_2K_2fdfaccf*")
SENS = ("ship", "dutch_ship_medium_2K_b67c0a0d*")
RES_H = RES_W * 9 // 16


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def prep_render() -> None:
    sc = bpy.context.scene
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    # render_still(ss) はシーン解像度で描いて 1/ss に縮める。
    # 解像度を ss 倍にするのは呼ぶ側の仕事
    sc.render.resolution_x = RES_W * SS
    sc.render.resolution_y = RES_H * SS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.use_nodes = True


def spin_render(tag: str, piv, n: int, spin: float, start_deg=32.0) -> None:
    sc = bpy.context.scene
    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    for f in range(n):
        piv.rotation_euler = (0.0, 0.0,
                              math.radians(start_deg + 360.0 * spin * f / n))
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, d / f"f{f:04d}.png", SS)
    say(f"  {tag} {n}枚")


def shot_hero() -> dict:
    blend = dm.find_blend(HERO[1])
    meshes, _ = dm.load(blend)
    dm.grey(meshes)
    piv = dm.stage(meshes)
    sec = dm.setup_lines(meshes)
    nf = sum(len(o.data.polygons) for o in meshes if not o.hide_render)
    say(f"hero: 面{nf:,} STEP0 {sec:.1f}秒")
    prep_render()
    spin_render("hero_line", piv, FRAMES, 0.34)
    return {"tag": "hero", "faces": nf, "step0": round(sec, 1)}


def shot_sens() -> dict:
    """同じ回転を、感度を変えて2本撮る。v2.7 の変更そのもの。"""
    blend = dm.find_blend(SENS[1])
    meshes, _ = dm.load(blend)
    dm.grey(meshes)
    piv = dm.stage(meshes)
    sec = dm.setup_lines(meshes)
    nf = sum(len(o.data.polygons) for o in meshes if not o.hide_render)
    say(f"sens: 面{nf:,} STEP0 {sec:.1f}秒")
    prep_render()
    sc = bpy.context.scene
    for value, name in ((1.0, "sens_100"), (0.5, "sens_050")):
        sc.fp_line_sensitivity = value
        bpy.context.view_layer.update()
        say(f"  感度 {sc.fp_line_sensitivity}")
        spin_render(name, piv, FRAMES, 0.34)
    return {"tag": "sens", "faces": nf, "step0": round(sec, 1)}


def main() -> None:
    fp_batch.install_addon()
    rows = []
    if ONLY in (None, "hero"):
        rows.append(shot_hero())
    if ONLY in (None, "sens"):
        rows.append(shot_sens())
    (OUT / "shots.json").write_text(json.dumps(
        {"res": [RES_W, RES_H], "frames": FRAMES, "rows": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
