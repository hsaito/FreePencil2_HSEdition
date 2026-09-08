"""Apply の有無で同じ絵が出る角度を探す。

サブディビジョンは1段ごとに角を分割するので、ケージで60度だった特徴は
Apply 後には小さい角度に分かれる。ならば必要なしきい値も段数分だけ
下がるはず。基準(付けたまま・60度)と並べて、どの角度で一致するかを見る。

同時に p50(二面角の中央値)も出す。もし「良いしきい値 / p50」が
ケージと Apply 後で同じなら、p50 に比例させれば面の細かさに依存せず
決められることになる。

    blender -b --factory-startup --python eval_match_subdiv.py -- [--levels 2]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "match_subdiv"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "700"))
LEVELS = int(arg("--levels", "2"))
BASE_DEG = float(arg("--base", "60.0"))
T0 = time.time()

SHAPES = [
    ("スザンヌ", lambda: (bpy.ops.mesh.primitive_monkey_add(),
                      bpy.context.object)[1]),
    ("トーラス", lambda: (bpy.ops.mesh.primitive_torus_add(),
                      bpy.context.object)[1]),
    ("円柱", lambda: (bpy.ops.mesh.primitive_cylinder_add(),
                    bpy.context.object)[1]),
]

# Apply 後に試す角度。段数2なら 60/4=15 あたりが当たりのはず
APPLIED_DEGS = [60.0, 40.0, 30.0, 20.0, 15.0, 10.0, 7.0]


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def fit(o):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    pts = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    ctr = (mn + mx) * 0.5
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 1e-4)
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 50.0
    cd.clip_end = size * 40
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    d = Vector((0.75, -1.0, 0.45)).normalized()
    cam.location = ctr + d * (size * 2.1)
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.lights.new("L", type="AREA")
    lt.energy = size * size * 900.0
    lt.size = size * 2.0
    lo = bpy.data.objects.new("L", lt)
    bpy.context.scene.collection.objects.link(lo)
    lo.location = ctr + Vector((0.4, -0.8, 1.4)) * size


def one(tag, make, applied, deg, key):
    from freepencil2 import mesh_islands
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    o = make()
    m = o.modifiers.new("Sub", type="SUBSURF")
    m.levels = m.render_levels = LEVELS
    if applied:
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)

    topo = mesh_islands.MeshTopology(o.data)
    ang = topo.angle_samples_deg()
    p50 = float(np.percentile(np.array(ang), 50)) if ang else 0.0

    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False
    scene.fp_auto_sharp = False
    scene.fp_sharp_auto = False
    scene.fp_sharp_edges = deg
    scene.fp_curve_blur = 0

    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    fit(o)
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{tag}_{key}.png"
    fp_batch.render_still(scene, png, 1)
    return {"file": png.name, "deg": deg, "p50": round(p50, 2),
            "faces": len(o.data.polygons),
            "ratio": round(deg / max(p50, 1e-6), 2)}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"m{i:02d}"
        shots = {}
        shots["base"] = one(tag, make, False, BASE_DEG, "base")
        say(f"{label} 基準(付けたまま {BASE_DEG:.0f}度) "
            f"p50={shots['base']['p50']} 比={shots['base']['ratio']} "
            f"{shots['base']['faces']}面")
        for d in APPLIED_DEGS:
            k = f"a{d:.0f}"
            shots[k] = one(tag, make, True, d, k)
        a = shots[f"a{APPLIED_DEGS[0]:.0f}"]
        say(f"{label} Apply済み p50={a['p50']} {a['faces']}面 / "
            + " ".join(f"{d:.0f}度(比{shots[f'a{d:.0f}']['ratio']})"
                       for d in APPLIED_DEGS))
        rows.append({"label": label, "tag": tag, "shots": shots})
    (OUT / "index.json").write_text(
        json.dumps({"levels": LEVELS, "base_deg": BASE_DEG,
                    "applied_degs": APPLIED_DEGS, "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
