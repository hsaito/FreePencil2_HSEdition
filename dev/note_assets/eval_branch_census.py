"""60体が choose_auto_threshold のどの枝に落ちるかを数える。

人工分割の下限(fp_auto_split_floor)が効くのは「一様に滑らか」の枝
だけ。稜線の起伏は全モデルに効く。両方を同時に既定へ入れるかどうかを
決めるには、下限がそもそも何体に触るのかを知る必要がある。

判定を写し取ると本体とずれるので、本物の choose_auto_threshold を
包んで、渡された引数と返り値をそのまま記録する。レンダはしない。

  blender -b --factory-startup --python eval_branch_census.py -- [--limit 60]
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
OUT = Path(arg("--out", str(HERE / "out" / "branch"))).resolve()
LIMIT = int(arg("--limit", "60"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", "256", "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()
LOG = []


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def install_probe():
    """本物の判定を包んで、どの枝を通ったかを引数から言い当てる。"""
    from freepencil2 import utils, vertex_color
    real = utils.choose_auto_threshold

    def probe(angles_deg, has_armature=False, many_parts=False,
              has_subsurf=False, split_floor=None):
        deg, merge = real(angles_deg, has_armature, many_parts,
                          has_subsurf, split_floor)
        s = sorted(angles_deg)
        n = max(len(s), 1)

        def pct(p):
            return s[min(n - 1, int(n * p / 100))] if s else 0.0

        if not angles_deg:
            b = "角度なし"
        elif has_armature:
            b = "リグ"
        elif pct(90) > 100.0:
            b = "交差"
        elif pct(95) > 75.0:
            b = "構造線"
        elif pct(99) > 45.0:
            b = "曲率"
        elif many_parts:
            b = "多パーツ"
        elif has_subsurf:
            b = "サブサーフ"
        else:
            b = "人工分割"
        # 下限が実際に効いた(p50×0.95 より上へ持ち上げられた)か
        raw = pct(50) * 0.95
        bound = b == "人工分割" and raw < float(
            split_floor if split_floor is not None
            else utils.ARTIFICIAL_SPLIT_FLOOR)
        LOG.append({"branch": b, "deg": round(float(deg), 2),
                    "raw": round(float(raw), 2), "bound": bool(bound)})
        return deg, merge

    utils.choose_auto_threshold = probe
    vertex_color.utils.choose_auto_threshold = probe


def main():
    fp_batch.install_addon()
    install_probe()
    models = scan_models.scan(scan_models.DEFAULT_ROOT)[:LIMIT]
    rows = []
    for m in models:
        name = Path(m["path"]).stem[:28]
        LOG.clear()
        try:
            meshes, _ = dm.load(m["path"])
            dm.grey(meshes)
        except Exception as e:                    # noqa: BLE001
            say(f"{name}: 読めない {type(e).__name__}")
            continue
        sc = bpy.context.scene
        sc.fp_use_random_seed = False
        sc.fp_color_seed = 42
        sc.fp_enable_compositor_view = False
        sc.fp_auto_detect_aov = False
        sc.fp_auto_supersample = False
        sc.fp_supersample = False
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        try:
            bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        except Exception as e:                    # noqa: BLE001
            say(f"{name}: STEP0 失敗 {type(e).__name__}")
            continue
        hits = {}
        for r in LOG:
            hits[r["branch"]] = hits.get(r["branch"], 0) + 1
        if not hits:
            say(f"{name}: 自動しきい値を通らなかった")
            continue
        art = hits.get("人工分割", 0)
        bound = sum(1 for r in LOG if r["bound"])
        tot = sum(hits.values())
        top = max(hits.items(), key=lambda kv: kv[1])[0]
        rows.append({"model": name, "hits": hits, "top": top,
                     "artificial": art, "bound": bound, "objects": tot,
                     "raw": [r["raw"] for r in LOG if r["branch"] == "人工分割"]})
        say(f"{name:<30} 主 {top:<6} 人工分割 {art}/{tot}  下限が効いた {bound}")
    (OUT / "branch.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    n_any = sum(1 for r in rows if r["artificial"] > 0)
    n_bound = sum(1 for r in rows if r["bound"] > 0)
    say("")
    say(f"{len(rows)}体  人工分割の枝に落ちるオブジェクトを持つ {n_any}体  "
        f"うち下限が実際に効いた {n_bound}体")
    raws = [x for r in rows for x in r["raw"]]
    if raws:
        a = np.array(raws)
        say(f"人工分割の生の角度 p50x0.95: 中央 {np.median(a):.2f}度  "
            f"5度未満 {int((a < 5).sum())}件  14度未満 {int((a < 14).sum())}件  "
            f"全 {a.size}件")


if __name__ == "__main__":
    main()
