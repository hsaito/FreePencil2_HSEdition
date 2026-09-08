"""自動しきい値がモデルをどう分類しているかを、まとめて測る。

choose_auto_threshold は二面角の分布だけで4通りに分ける。その判定が
実アセットで妥当か(=島が過剰に切れていないか)を数字で見る。

「島/面」が 0.2 を超えると、面5枚に1島 = メッシュの網目がそのまま線に
なっている状態。スザンヌ(サブサーフ2)は 0.26 だった。

  blender -b --factory-startup --python eval_auto_type.py -- [--limit 40]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


LIMIT = int(arg("--limit", "40"))
OUT = Path(arg("--out", str(HERE / "out" / "autotype"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)


def branch_of(p50, p90, p95, p99, has_arm, many):
    """choose_auto_threshold のどの枝に落ちるかを名前で返す。"""
    if has_arm:
        return "rig"
    if p90 > 100.0:
        return "交差(葉)"
    if p95 > 75.0:
        return "メカ"
    if p99 > 45.0:
        return "有機"
    if many:
        return "多パーツ"
    return "★人工分割"


def main() -> None:
    fp_batch.install_addon()
    from freepencil2 import mesh_islands, utils
    from collections import Counter

    models = scan_models.scan(scan_models.DEFAULT_ROOT)[:LIMIT]
    rows = []
    for m in models:
        bpy.ops.wm.read_homefile(use_empty=True)
        try:
            meshes, others = fp_batch.append_objects(Path(m["path"]))
        except Exception as e:                    # noqa: BLE001
            print(f"[type] {m['name'][:30]} 読み込み失敗 {e}", flush=True)
            continue
        if not meshes:
            continue
        # 面数最大のメッシュを代表として見る
        obj = max(meshes, key=lambda o: len(o.data.polygons))
        me = obj.data
        if len(me.polygons) < 50:
            continue
        topo = mesh_islands.MeshTopology(me)
        ang = topo.angle_samples_deg()
        if not ang:
            continue
        a = np.array(ang)
        p50, p90, p95, p99 = (float(np.percentile(a, p))
                              for p in (50, 90, 95, 99))
        has_arm = any(md.type == "ARMATURE" and md.object
                      for md in obj.modifiers)
        deg, merge = utils.choose_auto_threshold(ang, has_armature=has_arm,
                                                 many_parts=False)
        nf = len(me.polygons)
        # 従来(分布だけで決め打ち)
        topo.mark_boundaries(math.radians(deg), False, False)
        topo.build_islands()
        n_isl = len(topo.islands)
        # 試し切りで収束させた場合
        t2 = mesh_islands.MeshTopology(me)
        deg2, tries, ratio2 = mesh_islands.resolve_threshold(
            t2, deg, False, False)
        n_isl2 = len(t2.islands)
        rows.append({
            "name": m["name"][:32], "faces": nf,
            "p50": round(p50, 1), "p90": round(p90, 1),
            "p95": round(p95, 1), "p99": round(p99, 1),
            "branch": branch_of(p50, p90, p95, p99, has_arm, False),
            "deg": round(deg, 1), "islands": n_isl,
            "isl_per_face": round(n_isl / nf, 4),
            "deg2": round(deg2, 1), "islands2": n_isl2,
            "isl_per_face2": round(n_isl2 / nf, 4), "tries": tries,
        })
        r = rows[-1]
        mark = "★" if r["isl_per_face"] > 0.2 else " "
        fix = "→改善" if r["isl_per_face2"] < r["isl_per_face"] * 0.9 else ""
        print(f"[type]{mark} {r['name']:<32} {r['branch']:<10} "
              f"従来 {r['deg']:>5.1f}度 島/面={r['isl_per_face']:.4f}  |  "
              f"試し切り {r['deg2']:>5.1f}度 島/面={r['isl_per_face2']:.4f} "
              f"({tries}回) {fix}", flush=True)

    (OUT / "result.json").write_text(json.dumps(rows, indent=1,
                                                ensure_ascii=False),
                                     encoding="utf-8")
    from collections import Counter
    c = Counter(r["branch"] for r in rows)
    bad = [r for r in rows if r["isl_per_face"] > 0.2]
    bad2 = [r for r in rows if r["isl_per_face2"] > 0.2]
    import statistics
    print(f"[type] 分類の内訳: {dict(c)}", flush=True)
    print(f"[type] 切れすぎ(島/面>0.2)  従来 {len(bad)}/{len(rows)}  "
          f"→ 試し切り {len(bad2)}/{len(rows)}", flush=True)
    print(f"[type] 島/面の中央値  従来 "
          f"{statistics.median(r['isl_per_face'] for r in rows):.4f}  "
          f"→ {statistics.median(r['isl_per_face2'] for r in rows):.4f}",
          flush=True)
    print(f"[type] 試行回数の分布: "
          f"{dict(Counter(r['tries'] for r in rows))}", flush=True)


if __name__ == "__main__":
    main()
