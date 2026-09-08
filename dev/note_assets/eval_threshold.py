"""しきい値の決め方を、丸いモデルとメカで見比べる。

スザンヌで「自動しきい値だと格子が出るか全部潰れるかの二択、手動20度だと
きれいに出る」と分かったので、それが他のモデルでも成り立つのかを見る。
曲面ぼかしが実際に効いているかも同時に確かめる(効いた辺の本数をログに出す)。

各モデルについて3通り描く。

  auto   いまの自動しきい値(resolve_threshold 込み)
  m20    手動20度
  m20b   手動20度 + 曲面ぼかし

判定は画像で行う。数値は見出しの目安にしか使わない(CLAUDE.md)。

    blender -b --factory-startup --python eval_threshold.py -- [--res 800]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "threshold"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "800"))
BLUR = int(arg("--blur", "10"))
DEG = float(arg("--deg", "20.0"))
T0 = time.time()

# (表示名, 種別, 引数)  種別 SUZANNE は引数がサブサーフ段数
ROUND_MODELS = [
    ("スザンヌ subsurf2", "SUZANNE", 2),
    ("スザンヌ 素", "SUZANNE", 0),
    ("アニメキャラ", "MODEL", "004_anime-girl"),
    ("野球ボール", "MODEL", "010_baseball"),
    ("サッカーボール", "MODEL", "030_dirty_football"),
    ("猫の置物", "MODEL", "024_cat_figurine"),
]
MECHA_MODELS = [
    ("カイノ メカ", "MODEL", "053_kaino"),
    ("ザク", "MODEL", "047_heavy-zaku"),
    ("戦車", "MODEL", "088_tank"),
    ("産業用ロボット", "MODEL", "076_robot-kuka"),
    ("Audi R8", "MODEL", "006_audi"),
    ("蒸気機関車", "MODEL", "052_jnr-c62"),
]

MODES = [
    ("auto", "自動しきい値(現行)", None, 0),
    ("m20", f"手動{DEG:.0f}度", DEG, 0),
    ("m20b", f"手動{DEG:.0f}度 + 曲面ぼかし{BLUR}", DEG, BLUR),
]


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def make_suzanne(levels):
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    if levels > 0:
        m = o.modifiers.new("S", type="SUBSURF")
        m.levels = m.render_levels = levels
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
    return [o]


def fit_camera(meshes):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
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
    cam.location = ctr + d * (size * 2.0)
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.lights.new("L", type="AREA")
    lt.energy = size * size * 700.0
    lt.size = size * 2.0
    lo = bpy.data.objects.new("L", lt)
    bpy.context.scene.collection.objects.link(lo)
    lo.location = ctr + Vector((0.4, -0.8, 1.4)) * size


def one(tag, kind, ref, mode, models):
    key, _label, deg, blur = mode
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    if kind == "SUZANNE":
        meshes = make_suzanne(ref)
    else:
        m = next((x for x in models if x["name"].startswith(ref)), None)
        if m is None:
            return None
        meshes, _o = fp_batch.append_objects(Path(m["path"]))
        # 非表示や空のメッシュを混ぜるとバウンディングボックスが跳ね、
        # 被写体が米粒になる(アニメキャラで実際に外した)
        meshes = [x for x in meshes
                  if not x.hide_render and len(x.data.polygons)]
        if not meshes:
            return None

    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False
    # STEP0 のおすすめ設定は fp_sharp_auto を True に戻すので切る
    scene.fp_auto_sharp = False
    scene.fp_sharp_auto = (deg is None)
    if deg is not None:
        scene.fp_sharp_edges = deg
    scene.fp_curve_blur = blur
    scene.fp_curve_blur_angle = 25.0

    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    fit_camera(meshes)
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    png = OUT / f"{tag}_{key}.png"
    fp_batch.render_still(scene, png, 1)
    faces = sum(len(o.data.polygons) for o in meshes)
    return {"file": png.name, "faces": faces}


def main():
    fp_batch.install_addon()
    models = scan_models.scan(scan_models.DEFAULT_ROOT)
    rows = []
    for group, items in (("丸い", ROUND_MODELS), ("メカ", MECHA_MODELS)):
        for i, (label, kind, ref) in enumerate(items):
            tag = f"{group}_{i:02d}"
            shots = {}
            for mode in MODES:
                try:
                    r = one(tag, kind, ref, mode, models)
                except Exception as e:                 # noqa: BLE001
                    say(f"{label} {mode[0]}: 失敗 {e}")
                    r = None
                if r:
                    shots[mode[0]] = r
            if shots:
                rows.append({"group": group, "label": label, "tag": tag,
                             "shots": shots})
                say(f"{group} {label:<16} {len(shots)}通り 描いた")
    (OUT / "index.json").write_text(
        json.dumps({"modes": [[m[0], m[1]] for m in MODES], "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
