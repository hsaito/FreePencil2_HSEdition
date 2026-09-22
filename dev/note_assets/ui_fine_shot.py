"""生成後に「細い線」を動かせることを、GUI の Blender で見せる。

サイドバーを開いて FreePencil タブの STEP3 を出し、スライダーを 0 と
0.6 にして、そのたびにビューポート(レンダー表示+コンポジタ)ごと
窓を撮る。レンダは回さない。

  blender --factory-startup -p 0 0 2560 1440 <town.blend> \
      --python ui_fine_shot.py -- --out <dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", ".")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
VALUES = [float(v) for v in arg("--values", "0,0.6").split(",")]
LOG = OUT / "ui_fine.log"
LOG.write_text("", encoding="utf-8")


def log(m):
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


ADDON_MODULE = "bl_ext.user_default.freepencil2"


def enable_addon():
    """--factory-startup では拡張機能が無効なので、実機の物を有効化する。"""
    import addon_utils
    for mod in (ADDON_MODULE, "freepencil2"):
        try:
            addon_utils.enable(mod, default_set=False, persistent=True)
            if hasattr(bpy.context.scene, "fp_fine_lines"):
                log(f"addon enabled: {mod}")
                return True
        except Exception as e:                       # noqa: BLE001
            log(f"enable {mod}: {e}")
    return hasattr(bpy.context.scene, "fp_fine_lines")


def win():
    return bpy.context.window_manager.windows[0]


def view3d():
    return next((a for a in win().screen.areas if a.type == "VIEW_3D"), None)


state = {"t": 0, "i": 0, "shot_at": None}


def tick():
    state["t"] += 1
    area = view3d()
    if area is None:
        bpy.ops.wm.quit_blender()
        return None
    space = area.spaces[0]
    region = next(r for r in area.regions if r.type == "WINDOW")
    if state["t"] == 1:
        if not enable_addon():
            log("addon が有効にならない")
            bpy.ops.wm.quit_blender()
            return None
        bpy.ops.object.select_all(action="DESELECT")
        space.show_region_ui = True
        space.overlay.show_overlays = False      # 選択の輪郭やグリッドを消す
        space.show_gizmo = False
        space.shading.type = "RENDERED"
        space.shading.use_compositor = "ALWAYS"
        with bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region):
            bpy.ops.view3d.view_camera()
            bpy.ops.view3d.view_center_camera()
        return 1.0
    if state["t"] == 2:
        # サイドバーの FreePencil タブを出し、STEP3 だけ開く。パネルの開閉は
        # API から触れないので、DEFAULT_CLOSED を外して登録し直す
        for r in area.regions:
            if r.type == "UI":
                try:
                    r.active_panel_category = "FreePencil"
                except (AttributeError, TypeError):
                    pass
        names = ["FREEPENCIL_PT_STEP0", "FREEPENCIL_PT_STEP1", "FREEPENCIL_PT_STEP2",
                 "FREEPENCIL_PT_STEP3", "FREEPENCIL_PT_STEP4", "FREEPENCIL_PT_CAMERAS"]
        originals = {n: getattr(bpy.types, n) for n in names if hasattr(bpy.types, n)}
        for cls in originals.values():
            bpy.utils.unregister_class(cls)
        for n, base in originals.items():
            opts = set() if n == "FREEPENCIL_PT_STEP3" else {"DEFAULT_CLOSED"}
            newc = type(base.__name__ + "_V1", (base,),
                        {"bl_idname": n + "_V1", "bl_options": opts})
            bpy.utils.register_class(newc)
        log("panels ready")
        return 1.0
    if state["t"] < 8:
        return 1.0
    # 値を入れて、数ティック待ってから撮る(スライダーの表示と絵を揃える)
    if state["shot_at"] is None:
        if state["i"] >= len(VALUES):
            bpy.ops.wm.quit_blender()
            return None
        v = VALUES[state["i"]]
        bpy.context.scene.fp_fine_lines = v
        for a_ in win().screen.areas:
            a_.tag_redraw()
        state["shot_at"] = state["t"] + 25   # ビューポートの再描画を待つ(短いと白いまま撮れた)
        log(f"set {v}")
        return 1.0
    if state["t"] >= state["shot_at"]:
        v = VALUES[state["i"]]
        with bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region):
            bpy.ops.screen.screenshot(filepath=str(OUT / f"ui_fine_{v:g}.png"))
        log(f"shot {v}")
        state["i"] += 1
        state["shot_at"] = None
    return 1.0


bpy.app.timers.register(tick, first_interval=2.0)
