"""ファイル出力と STEP5(カメラ一括レンダー)を最後まで通す。

カメラ 2 台の場面を保存し、仕上がりごとに STEP0 -> ファイル出力を ON(4 パス)->
STEP3 -> STEP5 を押し、書き出されたファイルを並べた画像を作る。大きさ(2倍レンダ
なら最終サイズで書くはず)と、パスごとの中身を目で見る。

  blender -b --factory-startup --python check_step5.py -- --out out/step5/<tag>
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "step5" / "now"))).resolve()
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
report = []
for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.0, 0, 0.9))
    mk = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
    cb = bpy.context.object
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 4, 0))
    for i, (loc, rot) in enumerate((((0, -6, 1.6), (82, 0, 0)), ((5, -4, 2.2), (78, 0, 50)))):
        cam = bpy.data.objects.new(f"Cam{i+1}", bpy.data.cameras.new(f"Cam{i+1}"))
        sc.collection.objects.link(cam)
        cam.location = loc
        cam.rotation_euler = tuple(math.radians(v) for v in rot)
    sc.camera = bpy.data.objects["Cam1"]
    lt = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN"))
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(45), 0, math.radians(30))
    sc.render.resolution_x, sc.render.resolution_y = 480, 270
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 3
    bpy.ops.object.select_all(action="DESELECT")
    for o in (mk, cb):
        o.select_set(True)
    bpy.context.view_layer.objects.active = mk
    sc.fp_auto_style = style
    blend = OUT / f"{style}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_file_output = True
    for k in ("fp_fo_line", "fp_fo_color", "fp_fo_light", "fp_fo_shadow"):
        setattr(sc, k, True)
    bpy.ops.freepencil2.link_button()
    bpy.ops.wm.save_mainfile()
    rec = {"style": style, "supersample": sc.fp_supersample,
           "res": [sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage]}
    try:
        rec["result"] = sorted(bpy.ops.freepencil.render_cameras())
    except Exception as e:      # noqa: BLE001
        rec["error"] = str(e)[:400]
    files = sorted(p.relative_to(OUT) for p in (OUT / "camera_renders").rglob("*") if p.is_file())
    rec["files"] = [str(p) for p in files]
    # 押したあと、設定が元に戻っているか(カメラ・書き出し先)
    rec["camera_after"] = sc.camera.name
    rec["pct_after"] = sc.render.resolution_percentage
    shutil.move(str(OUT / "camera_renders"), str(OUT / f"renders_{style}")) if (OUT / "camera_renders").exists() else None
    report.append(rec)
    print("@@@", json.dumps(rec, ensure_ascii=False), flush=True)
(OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
