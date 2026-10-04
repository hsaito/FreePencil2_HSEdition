"""配布 ZIP の新規インストール・v2.7 からの上書き・保存して開き直し を、別プロセスで1段ずつ通す。

Blender の中で1段ずつ呼ばれる(外側のドライバが BLENDER_USER_RESOURCES を空の
フォルダに向けて起動する。本物のプロファイルには触らない)。

  blender -b --python check_install.py -- --phase <名前> --out <dir> [--zip <zip>] [--blend <file>]

phase:
  install    ZIP を入れて有効にし、設定を保存する
  version    入っているアドオンの版とパネルの題を書く
  make       場面を作り、仕上がり(--style)で STEP0 を押して撮り、保存する
  touch      開いた .blend を何も触らずに撮る -> STEP3 -> STEP0(精密) を撮る
  tweak      開いた .blend の設定をいくつか変えて撮り、設定を書き、保存する
  reopen     開いた .blend の設定を書き、何も触らずに撮る -> つまみを1つ動かして撮る
"""
from __future__ import annotations

import json
import math
import sys
import traceback
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
PHASE = arg("--phase")
OUT = Path(arg("--out")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
MODULE = "bl_ext.user_default.freepencil2"

import bpy  # noqa: E402

rec = {"phase": PHASE, "blender": bpy.app.version_string}
PROPS = ("fp_auto_style", "fp_preview_mode", "fp_lw_strength", "fp_lw_far_amount", "fp_lw_relief",
         "fp_fine_lines", "fp_line_weight", "fp_file_output", "fp_lw_far", "fp_lw_dense",
         "fp_lw_stripe_fade", "fp_white_preview", "fp_supersample")


def render(name):
    sc = bpy.context.scene
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    rec.setdefault("renders", []).append(name)


def props():
    sc = bpy.context.scene
    d = {k: (round(getattr(sc, k), 4) if isinstance(getattr(sc, k, None), float) else getattr(sc, k, None))
         for k in PROPS if hasattr(sc, k)}
    d["paint_as"] = {o.name: getattr(o, "fp_paint_as", None) for o in sc.objects if o.type == "MESH"}
    return d


def select_meshes():
    sc = bpy.context.scene
    ms = [o for o in sc.objects if o.type == "MESH" and o.name != "Ground"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]


try:
    if PHASE == "install":
        try:
            bpy.ops.preferences.addon_disable(module=MODULE)
        except Exception:     # noqa: BLE001  入っていなければ何もしない
            pass
        bpy.ops.extensions.package_install_files(filepath=arg("--zip"), repo="user_default",
                                                 enable_on_install=True)
        bpy.ops.wm.save_userpref()
        rec["ok"] = True
    elif PHASE == "version":
        mod = sys.modules.get(MODULE)
        rec["loaded"] = mod is not None
        if mod is not None:
            rec["version"] = list(mod.ADDON_VERSION)
            rec["panel"] = bpy.types.FREEPENCIL_PT_LINE.bl_label
    elif PHASE == "make":
        bpy.ops.wm.read_homefile(use_empty=True)
        sc = bpy.context.scene
        bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.0, 0, 0.9))
        bpy.ops.object.shade_smooth()
        bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
        bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 4, 0))
        bpy.context.object.name = "Ground"
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.location = (0, -6, 1.6)
        cam.rotation_euler = (math.radians(82), 0, 0)
        lt = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN"))
        sc.collection.objects.link(lt)
        lt.rotation_euler = (math.radians(45), 0, math.radians(30))
        sc.render.resolution_x, sc.render.resolution_y = 480, 270
        for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
            if hasattr(sc, p_):
                setattr(sc, p_, False)
        sc.fp_color_seed = 3
        select_meshes()
        if arg("--style") and hasattr(sc, "fp_auto_style"):
            sc.fp_auto_style = arg("--style")
        bpy.ops.wm.save_as_mainfile(filepath=arg("--blend"))
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        render(arg("--name", "made"))
        bpy.ops.wm.save_mainfile()
        rec["props"] = props()
    elif PHASE == "touch":
        bpy.ops.wm.open_mainfile(filepath=arg("--blend"))
        rec["props_open"] = props()
        render("opened_untouched")
        bpy.ops.freepencil2.link_button()
        render("after_step3")
        select_meshes()
        bpy.context.scene.fp_auto_style = "PRECISE"
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        render("after_step0_precise")
        rec["props_after"] = props()
    elif PHASE == "tweak":
        bpy.ops.wm.open_mainfile(filepath=arg("--blend"))
        sc = bpy.context.scene
        sc.fp_preview_mode = "MONO_LIGHT"
        sc.fp_lw_strength = 0.8
        sc.fp_lw_far_amount = 0.5
        sc.fp_lw_relief = 0.7
        sc.fp_file_output = True
        bpy.data.objects["Cube"].fp_paint_as = "CHARA"
        bpy.ops.freepencil2.link_button()
        render("before_save")
        rec["props"] = props()
        bpy.ops.wm.save_mainfile()
    elif PHASE == "reopen":
        bpy.ops.wm.open_mainfile(filepath=arg("--blend"))
        rec["props"] = props()
        render("reopened_untouched")
        bpy.context.scene.fp_lw_strength = 0.4
        render("reopened_slider")
        rec["props_after_slider"] = props()
except Exception:             # noqa: BLE001
    rec["error"] = traceback.format_exc()[-1200:]
with (OUT / "log.jsonl").open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
print("@@@", json.dumps({k: v for k, v in rec.items() if k != "props"}, ensure_ascii=False)[:600], flush=True)
