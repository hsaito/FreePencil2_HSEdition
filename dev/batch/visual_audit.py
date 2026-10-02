"""見え方の監査(Blender の中で動く側)。決まった場面を撮って PNG に書く。

人が見て初めて見つかった不具合を、毎回撮って前回と並べるための場面:
  default_*      Blender の既定(背景が不透明)でスザンヌと溝の箱、仕上がり 3 つ
                 (背景が不透明だとキャラの強弱が出なかった、v2.8.2)
  ground_*       上に地面を足したもの(地平線の黒帯、v2.8.2)
  clear_bg       地面あり・背景を透過・手描き背景
  preview_*      キャラでプレビューを 白 -> モノクロ -> マテリアル -> 白 と切り替えた各段
                 (モノクロのあと白に戻らなかった、v2.8.2)
  facades_*      手前(30m)と奥(300m)の同じ壁(窓 36 個)、精密と手描き背景。_far_zoom は奥を望遠で
                 (遠い区画をまとめる、v2.9)

  blender -b --factory-startup --python visual_audit.py -- --out <dir>
外側から回すのは visual_audit_run.py(版ごとに回して基準と並べる)。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "visual_audit" / "now"))).resolve()
sys.path.insert(0, str(HERE))
import bpy        # noqa: E402
import fp_batch   # noqa: E402

RES = (960, 540)
log = {}


def new_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 7
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.eevee.taa_render_samples = 8
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(50), 0, math.radians(30))
    return sc


def camera(sc, loc, rot_deg, lens=35):
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = lens
    cam.location = loc
    cam.rotation_euler = tuple(math.radians(v) for v in rot_deg)
    sc.collection.objects.link(cam)
    sc.camera = cam


def monkey_and_box(ground=False):
    objs = []
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.2, 0, 0.9))
    bpy.ops.object.shade_smooth()
    objs.append(bpy.context.object)
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0.8, 0.3, 0.6))
    objs.append(bpy.context.object)
    for i in range(4):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.8, -0.31, 0.2 + i * 0.28))
        g = bpy.context.object
        g.scale = (1.0, 0.02, 0.03)
        objs.append(g)
    if ground:
        bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 60, 0))
        objs.append(bpy.context.object)
    return objs


def step0(sc, objs, style):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    sc.fp_auto_style = style
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")


def shot(sc, name):
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    log[name] = {"preview": sc.fp_preview_mode, "film_transparent": sc.render.film_transparent,
                 "style": sc.fp_auto_style}
    print("@@@", name, flush=True)


def facades():
    def one(name, x, y):
        bpy.ops.mesh.primitive_plane_add(size=10, location=(x, y, 5), rotation=(math.radians(90), 0, 0))
        parts = [bpy.context.object]
        for i in range(6):
            for j in range(6):
                bpy.ops.mesh.primitive_cube_add(size=1, location=(x - 3.75 + i * 1.5, y - 0.05, 1.25 + j * 1.5))
                w = bpy.context.object
                w.scale = (0.6, 0.1, 0.6)
                parts.append(w)
        bpy.ops.object.select_all(action="DESELECT")
        for o in parts:
            o.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        bpy.ops.object.join()
        bpy.context.object.name = name
        return bpy.context.object
    return [one("near", -9.0, 30.0), one("far", 40.0, 300.0)]


def main():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    for ground in (False, True):
        for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
            sc = new_scene()
            objs = monkey_and_box(ground)
            camera(sc, (0, -6, 1.6), (82, 0, 0))
            step0(sc, objs, style)
            shot(sc, f"{'ground' if ground else 'default'}_{style.lower()}")
    sc = new_scene()
    objs = monkey_and_box(True)
    camera(sc, (0, -6, 1.6), (82, 0, 0))
    sc.render.film_transparent = True
    step0(sc, objs, "BACKGROUND")
    shot(sc, "clear_bg")
    sc = new_scene()
    objs = monkey_and_box(True)
    camera(sc, (0, -6, 1.6), (82, 0, 0))
    step0(sc, objs, "WEIGHTED")
    for k, mode in enumerate(("WHITE", "MONO_LIGHT", "NONE", "WHITE")):
        sc.fp_preview_mode = mode
        shot(sc, f"preview_{k}_{mode.lower()}")
    for style in ("PRECISE", "BACKGROUND"):
        sc = new_scene()
        objs = facades()
        camera(sc, (0, 0, 5), (90, 0, 0), lens=24)
        step0(sc, objs, style)
        sc.fp_preview_mode = "WHITE"
        shot(sc, f"facades_{style.lower()}")
        # 奥の壁を望遠で(塗りは STEP0 のカメラで決まっているので、撮り方だけ変える)
        cam = sc.camera
        cam.data.lens = 300
        cam.rotation_euler = (math.radians(90), 0, math.atan2(-40.0, 300.0))
        shot(sc, f"facades_{style.lower()}_far_zoom")
    import addon_utils  # noqa: F401
    mod = sys.modules.get(next((m for m in sys.modules if m.endswith("freepencil2")), ""), None)
    log["_meta"] = {"blender": bpy.app.version_string,
                    "addon": ".".join(map(str, getattr(mod, "ADDON_VERSION", ()))) if mod else "?"}
    (OUT / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print("@@@ done", flush=True)


main()
