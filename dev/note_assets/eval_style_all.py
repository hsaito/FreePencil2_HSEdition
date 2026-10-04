"""BlenderKit 60体で、STEP0 の仕上がり「精密」「強弱」を回して並べる。

何も上書きせず、プルダウンを切り替えて STEP0 を押しただけの絵。
使う人が見るものと同じ経路(細線化 ON、しきい値の計測は STEP0 の中)。

出すもの:
    <name>_precise.png / <name>_weighted.png
    all.json   1体ごとの数値(インク量、真っ黒率、測ったしきい値、
               強弱ノードの有無)

見るところ(絵で):
    - 太い所が黒い塊にならないか(詰まりの守り)
    - 線が途中で切れないか
    - 強弱が効いていない体(輪郭が細いまま)は無いか
    - 精密側が v2.7 のままか(強弱ノードが 0 個)

  blender -b --factory-startup --python eval_style_all.py -- \
      --out <dir> [--limit 60] [--res 900]
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
OUT = Path(arg("--out", str(HERE / "out" / "style_all"))).resolve()
RES = int(arg("--res", "900"))
LIMIT = int(arg("--limit", "60"))
ONLY = arg("--only", "")

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()
STYLES = (("precise", 'PRECISE'), ("weighted", 'WEIGHTED'))


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def stage(meshes):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes
           for c in o.bound_box if not o.hide_render]
    if not pts:
        raise RuntimeError("可視メッシュ無し")
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    ctr = Vector(((min(xs) + max(xs)) * .5, (min(ys) + max(ys)) * .5,
                  (min(zs) + max(zs)) * .5))
    r = max((p - ctr).length for p in pts)
    cd = bpy.data.cameras.new("C")
    cd.lens = 55.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(30.0)
    from bpy_extras.object_utils import world_to_camera_view

    def place(d):
        cam.location = (ctr.x + math.sin(a) * d, ctr.y - math.cos(a) * d,
                        ctr.z + d * 0.22)
        cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    d = r * 3.0
    for _ in range(3):
        place(d)
        m = max(max(abs(world_to_camera_view(sc, cam, p).x - .5) * 2,
                    abs(world_to_camera_view(sc, cam, p).y - .5) * 2)
                for p in pts)
        d *= m * 1.10
    place(d)
    cd.clip_end = d * 30
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (.5, .5, .52, 1)
        bg.inputs[1].default_value = .15
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = 0.0
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(62), 0, math.radians(40) + a)


def measure(path):
    img = bpy.data.images.load(str(path))
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        a = buf.reshape(h, w, 4).astype(np.float64)
    finally:
        bpy.data.images.remove(img)
    alpha = a[..., 3] > .5
    ink = (1.0 - a[..., :3].mean(axis=2)) * a[..., 3]
    on = ink > 0.15
    return {"ink_pct": round(float(on.sum()) / max(int(alpha.sum()), 1) * 100, 3),
            "black_rate": round(float((ink[on] > 0.85).mean()) * 100, 1) if on.any() else 0.0}


def lw_nodes(sc):
    from freepencil2 import compat, line_weight
    tree = compat.get_compositor_tree(sc)
    if tree is None:
        return 0
    return sum(1 for n in tree.nodes if n.label == line_weight.NODE_LABEL)


def run_one(path, style, png):
    meshes, _ = dm.load(path)
    dm.grey(meshes)
    stage(meshes)
    sc = bpy.context.scene
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.fp_white_preview = True
    sc.fp_auto_style = style
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    assert sc.render.resolution_percentage == 200
    fp_batch.render_still(sc, png, 1)
    m = measure(png)
    m["edges"] = [round(getattr(sc, f"fp_lw_e{i}"), 4) for i in range(1, 5)]
    m["lw_nodes"] = lw_nodes(sc)
    m["floor"] = sc.fp_auto_split_floor
    m["density"] = round(float(getattr(sc, "fp_lw_density", -1.0)), 4)
    m["ridge"] = round(sc.fp_ridge_amount, 2)
    return m


def main():
    fp_batch.install_addon()
    models = scan_models.scan(scan_models.DEFAULT_ROOT)[:LIMIT]
    if ONLY:
        pats = [x for x in ONLY.split(",") if x]
        models = [m for m in models if any(p in Path(m["path"]).stem for p in pats)]
    rows = []
    for m in models:
        name = Path(m["path"]).stem[:28]
        per = {}
        ok = True
        for tag, style in STYLES:
            try:
                per[tag] = run_one(m["path"], style, OUT / f"{name}_{tag}.png")
            except Exception as e:                       # noqa: BLE001
                say(f"{name}: {tag} 失敗 {type(e).__name__}: {e}")
                ok = False
                break
        if not ok:
            continue
        p, w = per["precise"], per["weighted"]
        flags = []
        if p["lw_nodes"] != 0:
            flags.append("精密に強弱ノード")
        if w["lw_nodes"] == 0:
            flags.append("強弱ノード無し")
        if w["edges"] == [0.0019, 0.0147, 0.0453, 0.1051]:
            flags.append("しきい値が既定のまま")
        if w["black_rate"] < p["black_rate"] + 10:
            flags.append("黒くならない")
        rows.append({"model": name, "precise": p, "weighted": w, "flags": flags})
        say(f"{name:<30} 真っ黒 {p['black_rate']:5.1f}->{w['black_rate']:5.1f}%  "
            f"インク {p['ink_pct']:6.2f}->{w['ink_pct']:6.2f}%  "
            f"密度 {w['density']:.3f}  しきい値 {w['edges']}  {' / '.join(flags)}")
    (OUT / "all.json").write_text(json.dumps(
        {"res": RES, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in rows if r["flags"]]
    say("")
    say(f"{len(rows)}体  印付き {len(bad)}体")
    for r in bad:
        say(f"   {r['model']:<30} {' / '.join(r['flags'])}")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
