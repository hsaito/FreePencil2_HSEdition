"""sample2 で「自動だと線が弱い」を切り分ける。

聞かれていること:
  1. なぜ自動だと線が弱いのか
  2. メカなら角度を小さめにできないか
  3. 25度はハイポリだとまずいのか
  4. 切り替えを自動で判定できないか

まずシーンの実態を測る。オブジェクトごとに面数・サブディビの有無・
二面角の分位点・自動が選ぶ角度と、その根拠になった枝を出す。
そのうえで角度を振って撮り、目で見て比べる(CLAUDE.md)。

    blender -b --factory-startup --python eval_sample2.py -- [--degs 25,30,40,60]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


SRC = Path(arg("--src", r"E:\10_cowork\00_code\22_FreePencil\sample\sample2.blend"))
OUT = Path(arg("--out", str(HERE / "out" / "sample2"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "1280"))
DEGS = [float(x) for x in arg("--degs", "25,30,40,60").split(",")]
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def survey():
    """シーンの実態を測る。自動がどの枝で角度を決めたかまで出す。"""
    from freepencil2 import mesh_islands, utils
    rows = []
    for o in [x for x in bpy.context.scene.objects if x.type == 'MESH']:
        me = o.data
        if not len(me.polygons):
            continue
        topo = mesh_islands.MeshTopology(me)
        ang = np.array(topo.angle_samples_deg(), dtype=np.float64)
        has_sub = any(m.type == 'SUBSURF' and m.show_viewport
                      for m in o.modifiers)
        has_arm = any(m.type == 'ARMATURE' and m.show_viewport and m.object
                      for m in o.modifiers)
        n_parts = utils.count_loose_parts(me, stop_at=9)
        deg, merge = utils.choose_auto_threshold(
            ang.tolist(), has_armature=has_arm, many_parts=n_parts >= 8,
            has_subsurf=has_sub)

        def pct(p):
            return float(np.percentile(ang, p)) if len(ang) else 0.0

        # どの枝に落ちたか。choose_auto_threshold と同じ順で判定する
        if has_arm:
            why = "リグ付き"
        elif pct(90) > 100.0:
            why = "p90>100 交差ジオメトリ"
        elif pct(95) > 75.0:
            why = "p95>75 構造エッジの山"
        elif pct(99) > 45.0:
            why = "p99>45 曲率の連続分布"
        elif n_parts >= 8:
            why = "多パーツ"
        elif has_sub:
            why = "サブディビあり"
        else:
            why = "一様に滑らか -> p50x0.95 で人工分割"

        # 25度で切ったときに境界になる辺の割合。ここが小さいほど
        # 「25度は少数派の構造線」= 下げても格子は出ない
        share25 = float((ang > 25.0).mean()) if len(ang) else 0.0
        share40 = float((ang > 40.0).mean()) if len(ang) else 0.0
        rows.append({
            "name": o.name, "faces": len(me.polygons),
            "subsurf": has_sub, "parts": n_parts,
            "p50": round(pct(50), 1), "p90": round(pct(90), 1),
            "p95": round(pct(95), 1), "p99": round(pct(99), 1),
            "auto": round(deg, 1), "why": why,
            "share25": round(share25, 4), "share40": round(share40, 4),
        })
    return rows


def render(key, deg):
    """deg=None なら自動。線画を1枚撮る。"""
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    sc = bpy.context.scene
    meshes = [o for o in sc.objects if o.type == 'MESH']
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_preview_mode = 'NONE'
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_sharp = False              # STEP0 に上書きさせない
    sc.fp_sharp_auto = deg is None
    if deg is not None:
        sc.fp_sharp_edges = deg

    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES * 2
    sc.render.resolution_y = int(RES * 9 / 16) * 2
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{key}_line.png"
    fp_batch.render_still(sc, png, 2)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    return png


def main():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    rows = survey()
    say(f"メッシュ {len(rows)}個 / 面 合計 {sum(r['faces'] for r in rows):,}")
    for r in rows:
        say(f"  {r['name'][:22]:<22} 面{r['faces']:>8,} "
            f"sub={'有' if r['subsurf'] else '無'} "
            f"p50={r['p50']:>5} p95={r['p95']:>5} p99={r['p99']:>5} "
            f"-> 自動{r['auto']:>5}度 ({r['why']}) "
            f"25度超の辺 {r['share25'] * 100:.1f}%")

    render("auto", None)
    say("自動 撮影")
    for d in DEGS:
        render(f"d{d:.0f}", d)
        say(f"{d:.0f}度 撮影")
    (OUT / "survey.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
