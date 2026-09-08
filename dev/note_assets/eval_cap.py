"""角度を下げる規則の上限(パーツあたりの島数)を、実モデル100体で検証する。

lower_threshold_for_detail は「島の数がパーツ数x上限を超えない範囲で、
島が最も多くなる最も高い角度」を採る。上限20はスザンヌ・箱・球・円柱の
4形状から決めた仮の値なので、実アセットで振り直す。

レンダはしない。角度と島の数だけを数える。

    blender -b --factory-startup --python eval_cap.py -- [--limit 105]
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "cap"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
LIMIT = int(arg("--limit", "105"))
CAPS = [int(x) for x in arg("--caps", "10,20,40,80").split(",")]
MODELS = Path(arg("--models", str(HERE.parent / "batch" / "out" / "models.json")))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def model_list():
    rows = json.loads(MODELS.read_text("utf-8"))
    out = []
    for r in rows:
        p = Path(r["path"])
        if p.exists():
            out.append((r["name"], p))
    return out[:LIMIT]


def survey_one(name, blend):
    from freepencil2 import mesh_islands, utils
    bpy.ops.wm.read_homefile(use_empty=True)
    meshes, others = fp_batch.append_objects(blend)
    rows = []
    for o in meshes:
        me = o.data
        nf = len(me.polygons)
        if nf < 4 or nf > 2_000_000:      # 平面と超重量級は除く
            continue
        topo = mesh_islands.MeshTopology(me)
        ang = topo.angle_samples_deg()
        has_sub = any(m.type == 'SUBSURF' and m.show_viewport
                      for m in o.modifiers)
        has_arm = any(m.type == 'ARMATURE' and m.object for m in o.modifiers)
        parts = utils.count_loose_parts(me)
        auto, _merge = utils.choose_auto_threshold(
            ang, has_armature=has_arm, many_parts=parts >= 8,
            has_subsurf=has_sub)
        # 上限ごとに、下げた先の角度と島数
        per_cap = {}
        for cap in CAPS:
            d, n = mesh_islands.lower_threshold_for_detail(
                topo, parts, False, False, cap_per_part=cap)
            per_cap[cap] = (None if d is None else round(d, 1), n)
        rows.append({
            "obj": o.name, "faces": nf, "parts": parts,
            "arm": has_arm, "sub": has_sub, "auto": round(auto, 1),
            "caps": {str(k): v for k, v in per_cap.items()},
            "guarded": bool(has_arm or parts >= 8),
        })
    return rows


def main():
    fp_batch.install_addon()
    all_rows = []
    for name, blend in model_list():
        try:
            rows = survey_one(name, blend)
        except Exception as e:                           # noqa: BLE001
            traceback.print_exc()
            say(f"{name[:34]}: 失敗 {e}")
            continue
        for r in rows:
            r["model"] = name
        all_rows.extend(rows)
        if rows:
            big = max(rows, key=lambda r: r["faces"])
            c = big["caps"][str(CAPS[1])]
            say(f"{name[:34]:<34} メッシュ{len(rows):>3} "
                f"最大{big['faces']:>8,}面 パーツ{big['parts']:>4} "
                f"自動{big['auto']:>5} -> 上限20で {c[0]}度 島{c[1]}"
                + ("  [ガード]" if big["guarded"] else ""))
    (OUT / "cap.json").write_text(
        json.dumps({"caps": CAPS, "rows": all_rows}, ensure_ascii=False,
                   indent=1), encoding="utf-8")
    say(f"完了 メッシュ {len(all_rows)}個 -> {OUT / 'cap.json'}")


if __name__ == "__main__":
    main()
