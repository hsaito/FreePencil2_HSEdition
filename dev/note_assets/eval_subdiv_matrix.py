"""プリミティブにサブディビジョンをかけて、自動しきい値の挙動を総当たりで見る。

BlenderKit のアセットは形状・モディファイア・スケールが混ざっていて、
どれが効いているのか切り分けられない。プリミティブなら他の要因が入らない。

条件は3つ。

  none    サブディビジョン無し
  live    モディファイアを付けたまま = Apply を押していない状態。
          STEP1 が見るのは元の粗いケージ
  applied Apply して細かいメッシュに焼き込んだ状態。
          STEP1 が見るのはその細かいメッシュ

同じ形で3枚並べれば、しきい値の判定がどちらへ転ぶかが一目で分かる。
判定は画像で行う(CLAUDE.md)。しきい値の数値は見出しに添えるだけ。

    blender -b --factory-startup --python eval_subdiv_matrix.py -- [--levels 2]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "subdiv_matrix"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "700"))
LEVELS = int(arg("--levels", "2"))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def add_plane_grid():
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=6, y_subdivisions=6)
    o = bpy.context.object
    # 平らなままだと二面角が全部ゼロで線の出しようが無いので、少し折る
    o.modifiers.new("W", type="WAVE")
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier="W")
    return o


SHAPES = [
    ("立方体", lambda: (bpy.ops.mesh.primitive_cube_add(),
                     bpy.context.object)[1]),
    ("UV球", lambda: (bpy.ops.mesh.primitive_uv_sphere_add(),
                     bpy.context.object)[1]),
    ("ICO球", lambda: (bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2),
                      bpy.context.object)[1]),
    ("円柱", lambda: (bpy.ops.mesh.primitive_cylinder_add(),
                    bpy.context.object)[1]),
    ("円錐", lambda: (bpy.ops.mesh.primitive_cone_add(),
                    bpy.context.object)[1]),
    ("トーラス", lambda: (bpy.ops.mesh.primitive_torus_add(),
                      bpy.context.object)[1]),
    ("スザンヌ", lambda: (bpy.ops.mesh.primitive_monkey_add(),
                      bpy.context.object)[1]),
    ("波打つ平面", add_plane_grid),
]

CONDS = [("none", "サブディビジョン無し"),
         ("live", f"サブディビジョン付き・未適用(段数{LEVELS})"),
         ("applied", f"サブディビジョンを適用済み(段数{LEVELS})")]


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


def one(tag, make, cond):
    from freepencil2 import mesh_islands, utils
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    o = make()
    if cond != "none":
        m = o.modifiers.new("Sub", type="SUBSURF")
        m.levels = m.render_levels = LEVELS
        if cond == "applied":
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.modifier_apply(modifier=m.name)

    # STEP1 が実際に見るのはベースメッシュ。同じ入力でしきい値を再現する
    topo = mesh_islands.MeshTopology(o.data)
    has_sub = any(md.type == 'SUBSURF' and md.show_viewport
                  for md in o.modifiers)
    deg, _merge = utils.choose_auto_threshold(
        topo.angle_samples_deg(), has_armature=False, many_parts=False,
        has_subsurf=has_sub)

    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False
    scene.fp_auto_sharp = False      # STEP0 が上書きするのを止める
    scene.fp_sharp_auto = True
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
    png = OUT / f"{tag}_{cond}.png"
    fp_batch.render_still(scene, png, 1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{tag}_{cond}.blend"))
    return {"file": png.name, "deg": round(deg, 1),
            "base_faces": len(o.data.polygons), "has_subsurf": has_sub}


def main():
    fp_batch.install_addon()
    rows = []
    for i, (label, make) in enumerate(SHAPES):
        tag = f"s{i:02d}"
        shots = {}
        for key, _cl in CONDS:
            try:
                shots[key] = one(tag, make, key)
            except Exception as e:                       # noqa: BLE001
                say(f"{label} {key}: 失敗 {e}")
        if shots:
            rows.append({"label": label, "tag": tag, "shots": shots})
            say(f"{label:<12} " + " / ".join(
                f"{k}:{v['deg']:.0f}度({v['base_faces']}面)"
                for k, v in shots.items()))
    (OUT / "index.json").write_text(
        json.dumps({"levels": LEVELS, "conds": CONDS, "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
