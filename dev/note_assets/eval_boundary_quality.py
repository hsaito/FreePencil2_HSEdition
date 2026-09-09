"""切った後の境界を見て、本物の折れ目と人工的な切れ目を分けられるか。

角度のしきい値を1つ選ぶやり方では、スザンヌの口と耳を両立できない
(1度刻みで確認済み: 口は10->11度で消え、耳は13->14度で直る)。
モデル全体を1つの角度で見ている限り、この2つは重ならない。

そこで見る場所を変える。低い角度で切ってしまってから、**できた境界
そのもの**を採点する。本物の折れ目なら境界に沿って二面角が高いはずで、
なめらかな面を横切っただけの切れ目なら、しきい値ぎりぎりの角度が
だらだら続くはず。そこが分かれるなら、後から捨てられる。

出すもの: 境界ごとの二面角の統計を、耳・口・その他に分けて並べる。

  blender -b --factory-startup --python eval_boundary_quality.py -- \
      [--subdiv 2] [--deg 6.2]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "boundary"))).resolve()
SUBDIV = int(arg("--subdiv", "2"))
DEG = float(arg("--deg", "6.2"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", "640", "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)


def say(m: str) -> None:
    print(f"@@@ {m}", flush=True)


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    if SUBDIV > 0:
        m = o.modifiers.new("S", "SUBSURF")
        m.levels = m.render_levels = SUBDIV
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o


def edge_angles(me):
    """辺ごとの二面角(度)と、両側の面の番号を返す。"""
    nf = len(me.polygons)
    nrm = np.empty(nf * 3, dtype=np.float64)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(nf, 3)
    ne = len(me.edges)
    ev = np.empty(ne * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(ne, 2)
    # 辺 -> 面。ループから引く
    nl = len(me.loops)
    le = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("edge_index", le)
    starts = np.empty(nf, dtype=np.int32)
    totals = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    fa = np.full(ne, -1, dtype=np.int32)
    fb = np.full(ne, -1, dtype=np.int32)
    for f, (s, t) in enumerate(zip(starts, totals)):
        for e in le[s:s + t]:
            if fa[e] < 0:
                fa[e] = f
            else:
                fb[e] = f
    two = (fa >= 0) & (fb >= 0)
    ang = np.zeros(ne)
    d = np.einsum("ij,ij->i", nrm[fa[two]], nrm[fb[two]])
    ang[two] = np.degrees(np.arccos(np.clip(d, -1.0, 1.0)))
    return ang, fa, fb, two, ev


def main() -> None:
    fp_batch.install_addon()
    from freepencil2 import mesh_islands
    o = build()
    me = o.data
    topo = mesh_islands.MeshTopology(me)
    topo.mark_boundaries(np.radians(DEG), False, False)
    topo.build_islands()
    lab = topo.labels
    say(f"面 {len(me.polygons)}  {DEG}度で切った島 {len(topo.islands)}")

    ang, fa, fb, two, ev = edge_angles(me)
    # 島の境目になった辺
    cut = np.zeros(len(me.edges), dtype=bool)
    cut[two] = lab[fa[two]] != lab[fb[two]]
    say(f"境界の辺 {int(cut.sum())} / 全辺 {len(me.edges)}")

    # 辺の位置。耳と口を場所で分ける
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)
    mid = (co[ev[:, 0]] + co[ev[:, 1]]) * 0.5
    ear = np.abs(mid[:, 0]) > 1.05
    # 口は鼻先の下。スザンヌの口元は前寄りで低い位置
    mouth = (np.abs(mid[:, 0]) < 0.55) & (mid[:, 1] < -0.55) & (mid[:, 2] < -0.25)
    other = ~ear & ~mouth

    say("")
    say(f"{'場所':<8}{'境界の辺':>9}{'二面角 中央':>12}{'75%':>8}{'90%':>8}"
        f"{'しきい値の何倍':>14}")
    rows = {}
    for name, sel in (("耳", ear), ("口もと", mouth), ("その他", other)):
        m = cut & sel
        n = int(m.sum())
        if n == 0:
            say(f"{name:<8}{n:>9}   境界なし")
            continue
        v = ang[m]
        med = float(np.median(v))
        rows[name] = {"edges": n, "median": round(med, 2),
                      "p75": round(float(np.percentile(v, 75)), 2),
                      "p90": round(float(np.percentile(v, 90)), 2),
                      "ratio": round(med / DEG, 2)}
        say(f"{name:<8}{n:>9}{med:>12.2f}{np.percentile(v, 75):>8.2f}"
            f"{np.percentile(v, 90):>8.2f}{med / DEG:>13.2f}倍")

    # 「折れているか、ゆるく曲がっているか」を距離で見る。
    #
    # 隣り合う面の角度だけでは分けられなかった(耳14.89度 > 口11.98度で
    # 逆になる)。折れ目は「曲がりが1本の辺に集中している」形、なめらかな
    # 面を横切っただけの切れ目は「同じ曲がりが何枚にも散らばっている」形。
    # 少し離れた面まで見た角度と、隣の面だけの角度の比を取ると分かれる。
    #
    #   集中している(折れ目)     隣の角度 / 離れた角度 が 1 に近い
    #   散らばっている(ゆるい曲面) 比が小さい
    nf = len(me.polygons)
    nrm = np.empty(nf * 3, dtype=np.float64)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(nf, 3)
    # 面の隣接。境界の辺はまたがない形で 3 リング広げる
    adj = [[] for _ in range(nf)]
    for e in np.where(two & ~cut)[0]:
        adj[fa[e]].append(fb[e])
        adj[fb[e]].append(fa[e])

    def ring_normal(seed, rings=3):
        seen = {seed}
        frontier = [seed]
        for _ in range(rings):
            nxt = []
            for f in frontier:
                for g in adj[f]:
                    if g not in seen:
                        seen.add(g)
                        nxt.append(g)
            frontier = nxt
        v = nrm[list(seen)].sum(axis=0)
        n = np.linalg.norm(v)
        return v / n if n > 1e-9 else nrm[seed]

    say("")
    say(f"{'場所':<8}{'隣の角度':>10}{'3リング先':>11}{'集中度':>9}")
    conc = {}
    for name, sel in (("耳", ear), ("口もと", mouth), ("その他", other)):
        idx = np.where(cut & sel)[0]
        if idx.size == 0:
            continue
        # 数が多いので間引いて測る
        step = max(1, idx.size // 300)
        near, far = [], []
        for e in idx[::step]:
            a, b = int(fa[e]), int(fb[e])
            near.append(ang[e])
            na, nb = ring_normal(a), ring_normal(b)
            d = float(np.clip(np.dot(na, nb), -1.0, 1.0))
            far.append(np.degrees(np.arccos(d)))
        near = np.array(near)
        far = np.array(far)
        ratio = near / np.maximum(far, 1e-6)
        conc[name] = {"near": round(float(np.median(near)), 2),
                      "far": round(float(np.median(far)), 2),
                      "conc": round(float(np.median(ratio)), 3)}
        say(f"{name:<8}{np.median(near):>10.2f}{np.median(far):>11.2f}"
            f"{np.median(ratio):>9.3f}")

    # 境界でない辺(=島の内側)の角度も出す。比較の基準になる
    inside = two & ~cut
    say("")
    say(f"島の内側の辺の二面角 中央 {np.median(ang[inside]):.2f}度"
        f"  (境界はこれより高いはず)")

    (OUT / "boundary.json").write_text(json.dumps(
        {"deg": DEG, "subdiv": SUBDIV, "islands": len(topo.islands),
         "rows": rows, "concentration": conc}, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
