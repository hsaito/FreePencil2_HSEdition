"""サイドバーの FreePencil パネルを 1 枚ずつ開いて、日本語と英語で撮る。

UI の棚卸し(本当に要るか)と翻訳漏れを画面で確かめるため。レンダしない。

  blender --factory-startup -p 0 0 1400 2100 <scene.blend> \
      --python ui_audit_shot.py -- --out <dir> [--langs ja_JP,en_US] [--scale 0.9]
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
LANGS = arg("--langs", "ja_JP,en_US").split(",")
SCALE = float(arg("--scale", "0.9"))
LOG = OUT / "ui_audit.log"
LOG.write_text("", encoding="utf-8")
ADDON_MODULE = "bl_ext.user_default.freepencil2"
PANELS = ["FREEPENCIL_PT_STEP0", "FREEPENCIL_PT_STEP1", "FREEPENCIL_PT_STEP2",
          "FREEPENCIL_PT_STEP3", "FREEPENCIL_PT_STEP4", "FREEPENCIL_PT_CAMERAS"]
# 子パネル(詳細)。親と一緒に登録し直す
CHILDREN = {"FREEPENCIL_PT_STEP0_OPTIONS": "FREEPENCIL_PT_STEP0",
            "FREEPENCIL_PT_STEP3_OPTIONS": "FREEPENCIL_PT_STEP3"}


def log(m):
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def enable_addon():
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


_originals = {}
_current = []


def open_only(name, details):
    """name のパネルだけ開いた状態で登録し直す(開閉は API から触れない)。

    details が真なら、その子パネル(詳細)も開く。
    """
    for cls in reversed(_current):
        bpy.utils.unregister_class(cls)
    _current.clear()
    if not _originals:
        for n in CHILDREN:
            if hasattr(bpy.types, n):
                _originals[n] = getattr(bpy.types, n)
                bpy.utils.unregister_class(_originals[n])
        for n in PANELS:
            if hasattr(bpy.types, n):
                _originals[n] = getattr(bpy.types, n)
                bpy.utils.unregister_class(_originals[n])
    k = state["job"]
    for n in PANELS + list(CHILDREN):
        base = _originals.get(n)
        if base is None:
            continue
        is_open = n == name or (details and CHILDREN.get(n) == name)
        attrs = {"bl_idname": f"{n}_A{k}",
                 "bl_options": set() if is_open else {"DEFAULT_CLOSED"}}
        if n in CHILDREN:
            attrs["bl_parent_id"] = f"{CHILDREN[n]}_A{k}"
        c = type(f"{base.__name__}_A{k}", (base,), attrs)
        bpy.utils.register_class(c)
        _current.append(c)


JOBS = [(lang, p, False) for lang in LANGS for p in PANELS]
JOBS += [(lang, p, True) for lang in LANGS for p in CHILDREN.values()]
state = {"t": 0, "job": 0, "shot_at": None}


def tick():
    state["t"] += 1
    area = view3d()
    if area is None:
        bpy.ops.wm.quit_blender()
        return None
    space = area.spaces[0]
    if state["t"] == 1:
        if not enable_addon():
            log("addon が有効にならない")
            bpy.ops.wm.quit_blender()
            return None
        prefs = bpy.context.preferences
        prefs.view.ui_scale = SCALE
        prefs.view.use_translate_interface = True
        prefs.view.use_translate_tooltips = True
        win_ = win()
        region = next(r for r in area.regions if r.type == "WINDOW")
        with bpy.context.temp_override(window=win_, screen=win_.screen, area=area, region=region):
            bpy.ops.screen.screen_full_area()
        area = view3d()
        space = area.spaces[0]
        space.show_region_ui = True
        space.shading.type = "SOLID"
        return 1.0
    if state["t"] < 4:
        return 1.0
    if state["shot_at"] is None:
        if state["job"] >= len(JOBS):
            bpy.ops.wm.quit_blender()
            return None
        lang, p, det = JOBS[state["job"]]
        bpy.context.preferences.view.language = lang
        open_only(p, det)
        for r in area.regions:
            if r.type == "UI":
                try:
                    r.active_panel_category = "FreePencil"
                except (AttributeError, TypeError):
                    pass
        for a_ in win().screen.areas:
            a_.tag_redraw()
        state["shot_at"] = state["t"] + 4
        return 1.0
    if state["t"] >= state["shot_at"]:
        lang, p, det = JOBS[state["job"]]
        ui = next(r for r in area.regions if r.type == "UI")
        path = OUT / f"{lang}_{p.split('_')[-1].lower()}{'_details' if det else ''}.png"
        region = next(r for r in area.regions if r.type == "WINDOW")
        with bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region):
            bpy.ops.screen.screenshot(filepath=str(path))
        # サイドバーの位置(窓の左下が原点)を残して、あとで切り出す
        log(f"shot {path.name} ui x={ui.x} y={ui.y} w={ui.width} h={ui.height} "
            f"win={win().width}x{win().height}")
        state["job"] += 1
        state["shot_at"] = None
    return 1.0


bpy.app.timers.register(tick, first_interval=2.0)
