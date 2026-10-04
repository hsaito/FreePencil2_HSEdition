"""リンク複製がどれくらい普通にあるかを数え、塗り分けへの影響を見る。

eggs_bowl を調べていて気づいた。vertex_color.py はメッシュを共有する
オブジェクトを1つにまとめてから塗る(75個の卵 -> 4メッシュ)。まとめる
こと自体は正しい(同じメッシュを何度塗っても同じ)。問題はその後で、

  - 多パーツ判定が「8個以上のオブジェクト」を数えられない
  - 近接隣接(隣り合うパーツに違う色を配る仕組み)も同じ理由で
    オブジェクト単位の隣接を見られない

隣り合う複製が同じ色になると、境界に色差が無いので線が出ない。
卵が団子になったのはこれだと思われる。まず「どれくらいの割合の
モデルがリンク複製を含むのか」を数える。話が卵1体だけなら放置でよく、
広いなら v2.8 で手を入れる価値がある。

  blender -b --factory-startup --python eval_linked_dupes.py -- [--limit 60]
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
OUT = Path(arg("--out", str(HERE / "out" / "dupes"))).resolve()
LIMIT = int(arg("--limit", "60"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", "256", "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def main():
    fp_batch.install_addon()
    rows = []
    for m in scan_models.scan(scan_models.DEFAULT_ROOT)[:LIMIT]:
        name = Path(m["path"]).stem[:28]
        try:
            meshes, _ = dm.load(m["path"])
        except Exception as e:                     # noqa: BLE001
            say(f"{name}: 読めない {type(e).__name__}")
            continue
        vis = [o for o in meshes if not o.hide_render and o.data.polygons]
        uniq = {o.data.name for o in vis}
        # まとめた結果、多パーツ判定(8以上)がひっくり返るか
        flips = len(vis) >= 8 > len(uniq)
        rows.append({"model": name, "objects": len(vis),
                     "meshes": len(uniq), "flips": flips})
        mark = "  ★多パーツ判定がひっくり返る" if flips else ""
        if len(vis) != len(uniq):
            say(f"{name:<30} オブジェクト {len(vis):>4} -> メッシュ "
                f"{len(uniq):>4}{mark}")
    (OUT / "dupes.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    dup = [r for r in rows if r["objects"] != r["meshes"]]
    flip = [r for r in rows if r["flips"]]
    say("")
    say(f"{len(rows)}体  リンク複製を含む {len(dup)}体  "
        f"うち多パーツ判定がひっくり返る {len(flip)}体")
    for r in flip:
        say(f"   {r['model']:<30} {r['objects']} -> {r['meshes']}")


if __name__ == "__main__":
    main()
