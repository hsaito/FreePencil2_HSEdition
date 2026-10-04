"""精密の自動しきい値が「切れすぎ」で 85 度を超えて上げられるメッシュを数える。

90 度の角が島の境界でなくなる = 箱の角に線が出ない。町の家やデッサン人形の
胴で起きた。BlenderKit 100 体で、どのメッシュがそうなるかを列挙する。
レンダはしない(STEP1 と同じ判定を配列で回すだけ)。

  blender -b --factory-startup --python eval_raise_census.py -- [--out out/raise_census.json]
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
OUT = Path(arg("--out", str(HERE / "out" / "raise_census.json"))).resolve()
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402


def main():
    fp_batch.install_addon()
    from freepencil2 import mesh_islands, utils
    models = json.load(open(HERE.parent / "batch" / "out" / "models.json", encoding="utf-8"))
    rows = []
    t0 = time.time()
    for m in models:
        name = Path(m["path"]).stem[:40]
        try:
            bpy.ops.wm.open_mainfile(filepath=m["path"])
        except Exception as e:                          # noqa: BLE001
            print(f"@@@ {name} open fail {e}", flush=True)
            continue
        meshes = [o for o in bpy.data.objects if o.type == "MESH"
                  and o.data and len(o.data.polygons) > 0]
        many = len(meshes) >= 8
        for o in meshes:
            topo = mesh_islands.MeshTopology(o.data)
            has_arm = any(md.type == 'ARMATURE' and md.object for md in o.modifiers)
            has_sub = any(md.type == 'SUBSURF' and md.show_viewport for md in o.modifiers)
            deg, _ = utils.choose_auto_threshold(
                topo.angle_samples_deg(), has_armature=has_arm, many_parts=many,
                has_subsurf=has_sub, split_floor=5.0)
            used, tries, ratio = mesh_islands.resolve_threshold(
                topo, deg, True, False, max_ratio=mesh_islands.MAX_ISLANDS_PER_FACE)
            n_parts = utils.count_loose_parts(o.data)
            if used > 85.0:
                # 90 度前後の辺がどれだけあるか(=失われる角)
                a = [x for x in topo.angle_samples_deg() if 80.0 <= x <= 100.0]
                rows.append({"model": name, "mesh": o.name, "faces": topo.n_faces,
                             "start": round(deg, 1), "used": round(used, 1),
                             "parts": n_parts, "right_angle_edges": len(a),
                             "ratio": round(ratio, 4)})
                print(f"@@@ {name[:28]:28s} {o.name[:24]:24s} faces={topo.n_faces:7d} "
                      f"{deg:.0f}->{used:.0f} parts={n_parts} 直角辺={len(a)}", flush=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"@@@ 完了 {len(rows)} メッシュ  {time.time() - t0:.0f}s -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
