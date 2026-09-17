"""葉(房にしてよい島)と、メカの細かい島を見分ける特徴を測る。

STEP0(キャラ)を回した後、mecha_color から島を戻し(同じ色で辺がつながる
面)、小さい島について 面数 と 平面性(法線の最大ずれ角) の分布を出す。

  blender -b --factory-startup --python eval_foliage_signature.py -- \
      [--only european-maple,coconut,tree_autumn,manchester,jnr-c62,anime-girl,lancia]
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
ONLY = arg("--only", "european-maple,coconut-tree,tree_autumn,manchester-acacia,jnr-c62,anime-girl,lancia-delta,police-car")
sys.argv = ["blender", "--", "--out", str(HERE / "out" / "sig"), "--res", "300", "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402

dm.OUT = HERE / "out" / "sig"
dm.OUT.mkdir(parents=True, exist_ok=True)


def islands_of(obj):
    from freepencil2 import mesh_islands
    me = obj.data
    nf, nl = len(me.polygons), len(me.loops)
    vc = me.color_attributes.get("mecha_color")
    if vc is None or nf == 0:
        return None
    buf = np.empty(nl * 4, dtype=np.float32)
    vc.data.foreach_get("color", buf)
    buf = buf.reshape(-1, 4)
    starts = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_start", starts)
    totals = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_total", totals)
    q = np.round(buf[starts, :3] * 255.0).astype(np.int64)
    colid = q[:, 0] * 65536 + q[:, 1] * 256 + q[:, 2]
    loop_edge = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("edge_index", loop_edge)
    loop_face = np.repeat(np.arange(nf, dtype=np.int32), totals)
    order = np.argsort(loop_edge, kind="stable")
    le, lf = loop_edge[order], loop_face[order]
    same = le[1:] == le[:-1]
    fa, fb = lf[:-1][same], lf[1:][same]
    keep = colid[fa] == colid[fb]
    isl = mesh_islands.connected_components(fa[keep], fb[keep], nf)
    area = np.empty(nf, dtype=np.float32)
    me.polygons.foreach_get("area", area)
    nrm = np.empty(nf * 3, dtype=np.float32)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    return isl, area, nrm


def main():
    fp_batch.install_addon()
    pats = [x for x in ONLY.split(",") if x]
    models = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
              if any(p in Path(m["path"]).stem for p in pats)]
    for m in models:
        name = Path(m["path"]).stem[:22]
        meshes, _ = dm.load(m["path"])
        sc = bpy.context.scene
        cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
        cam.location = (0, -30, 5)
        cam.rotation_euler = (1.4, 0, 0)
        sc.collection.objects.link(cam)
        sc.camera = cam
        sc.render.resolution_x = sc.render.resolution_y = 200
        for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
                   "fp_auto_detect_aov", "fp_auto_white_preview"):
            setattr(sc, p_, False)
        sc.fp_color_seed = 42
        sc.fp_auto_style = "BACKGROUND"
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        try:
            bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        except Exception as e:                       # noqa: BLE001
            print(f"@@@ {name}: STEP0 失敗 {e}")
            continue
        for o in meshes:
            got = islands_of(o)
            if got is None:
                continue
            isl, area, nrm = got
            n = int(isl.max()) + 1
            if n < 200:
                continue
            a_isl = np.bincount(isl, weights=area, minlength=n)
            total = float(a_isl.sum())
            small = np.nonzero(a_isl < total * 0.01)[0]
            if len(small) < 200:
                continue
            cnt = np.bincount(isl, minlength=n)
            # 平面性: 島の面積重み平均法線と各面法線の最大角
            sx = np.bincount(isl, weights=nrm[:, 0] * area, minlength=n)
            sy = np.bincount(isl, weights=nrm[:, 1] * area, minlength=n)
            sz = np.bincount(isl, weights=nrm[:, 2] * area, minlength=n)
            mean = np.stack([sx, sy, sz], 1)
            mean /= np.maximum(np.linalg.norm(mean, axis=1, keepdims=True), 1e-9)
            cosang = np.clip((nrm * mean[isl]).sum(1), -1, 1)
            ang = np.degrees(np.arccos(cosang))
            maxang = np.zeros(n)
            np.maximum.at(maxang, isl, ang)
            frac = float(a_isl[small].sum()) / total
            fc = cnt[small]
            pa = maxang[small]
            planar = float((pa < 15.0).mean())
            print(f"@@@ {name:<22} {o.name[:24]:<24} 島{n:6d} 小{len(small):6d} "
                  f"面積比{frac:4.2f} 面数中央{int(np.median(fc)):4d} p90{int(np.percentile(fc, 90)):5d} "
                  f"法線ずれ中央{np.median(pa):5.1f}° 平面(<15°){planar:4.2f}", flush=True)


if __name__ == "__main__":
    main()
