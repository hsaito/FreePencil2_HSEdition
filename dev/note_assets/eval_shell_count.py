"""人工分割の枝に落ちた4体とスザンヌで、メッシュのつながり方を比べる。

14度に上げるとスザンヌの耳は直るが eggs_bowl の卵が潰れる。角度では
分けられない(スザンヌの生角度 6.2度 < eggs_bowl 9.43度 で、下限を
どこに置いても両方は満たせない)。別の手がかりを探す。

見るのは「メッシュがいくつの塊でできているか」。卵の山は卵の数だけ
別々の殻に分かれているはずで、スザンヌは1枚の殻。塊が多いなら
人工分割が拾っているのは塊の境目そのものなので、下げてよい。

  blender -b --factory-startup --python eval_shell_count.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.argv = ["blender", "--", "--out", str(HERE / "out" / "shell"),
            "--res", "256", "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402

WANT = ["eggs_bowl", "basketball_2K", "cleaver_knife", "formal-shoe"]


def say(m):
    print(f"@@@ {m}", flush=True)


def shells(me):
    """面のつながり(辺を共有)で塊を数える。"""
    from freepencil2 import mesh_islands
    nl = len(me.loops)
    if not nl:
        return 0, []
    le = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("edge_index", le)
    nf = len(me.polygons)
    st = np.empty(nf, dtype=np.int32)
    tt = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_start", st)
    me.polygons.foreach_get("loop_total", tt)
    first = np.full(len(me.edges), -1, dtype=np.int32)
    ea, eb = [], []
    for f, (s, t) in enumerate(zip(st, tt)):
        for e in le[s:s + t]:
            if first[e] < 0:
                first[e] = f
            else:
                ea.append(first[e])
                eb.append(f)
    lab = mesh_islands.connected_components(
        np.array(ea, dtype=np.int32), np.array(eb, dtype=np.int32), nf)
    u, c = np.unique(lab, return_counts=True)
    return len(u), sorted(c.tolist(), reverse=True)[:5]


def report(tag, objs):
    for o in objs:
        me = o.data
        if not me.polygons:
            continue
        n, big = shells(me)
        say(f"{tag:<22} {o.name[:20]:<22} 面{len(me.polygons):>7}  "
            f"塊 {n:>5}  大きい順 {big}")


def main():
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("S", "SUBSURF")
    m.levels = m.render_levels = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    report("スザンヌ(subsurf2)", [o])
    for mm in scan_models.scan(scan_models.DEFAULT_ROOT):
        stem = Path(mm["path"]).stem
        if not any(w in stem for w in WANT):
            continue
        meshes, _ = dm.load(mm["path"])
        report(stem[:20], [x for x in meshes if not x.hide_render])


if __name__ == "__main__":
    main()
