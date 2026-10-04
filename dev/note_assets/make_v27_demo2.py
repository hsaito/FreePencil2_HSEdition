"""v2.7 の宣伝デモ、作り直し版の素材を撮る。

前の版が駄目だった理由:
  ・冒頭から線画で始まり、「線になる瞬間」が無い
  ・使ったモデルが過去のデモの使い回し(戦車・帆船・メカ)
  ・灰色の背景に灰色の陰影で、線が映えない
  ・被写体が枠の中で小さい

直したこと:
  ・hero は「陰影のみ」と「線画」を同じ回転で2本撮る(組み立て側でワイプ)
  ・未使用のモデルだけを使う
  ・白マテリアルプレビューを ON にして、白地に黒線にする
  ・背景を透過で描き、組み立て側で被写体だけ切り出して大きく置く

  blender -b --factory-startup --python make_v27_demo2.py -- \
      --out <dir> [--res 1600] [--ss 2] [--shot hero]
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
OUT = Path(arg("--out", str(HERE / "out" / "v27b"))).resolve()
RES_W = int(arg("--res", "1600"))
SS = int(arg("--ss", "2"))
ONLY = arg("--shot")

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W),
            "--ss", str(SS)]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()

# 試し撮り(probe_models.py)で線が濃く出たものだけ。
# 線がほとんど出なかった男性キャラ・骨格・ゾンビ・茶器は外した
HERO = ("scavenger", "space_scavenger*", 144)
MONTAGE = [
    # 試し撮り2巡で線が濃く出たものだけ。ザクは版権が明確なので外した。
    # かぼちゃ・イカ・キャラは回すと輪郭しか出ず、画面が持たなかった
    ("apartment", "japan-apartment*", 72),
    ("generator", "portable-generat*", 72),
    ("hangar", "arched_hangar*", 72),
    ("toytrain", "toy_train-02*", 72),
]


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def setup(meshes):
    """線を出す。白マテリアルプレビューを入れて、白地に黒線にする。"""
    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    # ここが前の版との違い。白マテリアルにすると、陰影が消えて
    # 線だけが残る。線画として一番よく見える状態
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    return time.time() - t


def prep_render() -> None:
    sc = bpy.context.scene
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    # render_still(ss) はシーン解像度で描いて 1/ss に縮める
    sc.render.resolution_x = RES_W * SS
    sc.render.resolution_y = RES_H * SS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    # 背景を抜く。組み立て側で被写体だけ切り出して大きく置きたい
    sc.render.film_transparent = True


def spin(tag: str, piv, n: int, turns: float, use_nodes: bool,
         start_deg: float = 28.0) -> None:
    sc = bpy.context.scene
    sc.use_nodes = use_nodes
    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    for f in range(n):
        piv.rotation_euler = (0.0, 0.0,
                              math.radians(start_deg + 360.0 * turns * f / n))
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, d / f"f{f:04d}.png", SS)
    say(f"  {tag} {n}枚")


def shot(tag: str, pattern: str, n: int, modes: list[str],
         turns: float) -> dict | None:
    blend = dm.find_blend(pattern)
    if blend is None:
        say(f"{tag}: 見つからない ({pattern})")
        return None
    meshes, _ = dm.load(blend)
    dm.grey(meshes)
    piv = dm.stage(meshes)
    sec = setup(meshes)
    nf = sum(len(o.data.polygons) for o in meshes if not o.hide_render)
    say(f"{tag}: 面{nf:,} STEP0 {sec:.1f}秒")
    prep_render()
    for mode in modes:
        # plain は合成を切る = 線が出ない。白プレビューも外して陰影を見せる
        sc = bpy.context.scene
        if mode == "plain":
            sc.fp_white_preview = False
        spin(f"{tag}_{mode}", piv, n, turns, use_nodes=(mode == "line"))
        if mode == "plain":
            sc.fp_white_preview = True
    return {"tag": tag, "faces": nf, "step0": round(sec, 1), "frames": n}


def main() -> None:
    fp_batch.install_addon()
    rows = []
    if ONLY in (None, "hero"):
        r = shot(HERO[0], HERO[1], HERO[2], ["plain", "line"], 0.30)
        if r:
            rows.append(r)
    if ONLY in (None, "montage"):
        for tag, pat, n in MONTAGE:
            r = shot(tag, pat, n, ["line"], 0.22)
            if r:
                rows.append(r)
    (OUT / "shots.json").write_text(json.dumps(
        {"res": [RES_W, RES_H], "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
