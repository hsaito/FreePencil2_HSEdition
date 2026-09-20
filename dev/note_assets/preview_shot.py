"""GUI の Blender でビューポートのプレビュー(コンポジタ込み)を撮る。レンダしない。

  blender --factory-startup -p 0 0 3840 2160 <town.blend> \
      --python preview_shot.py -- --out <png> [--wait 20]

細線化(0.5 の縮小)がプレビューにも掛かるので、絵は左下に半分の大きさで
出る。窓を 3840x2160 で開けば 1920x1080 の絵が撮れる(撮ったあと切り出す)。
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", "preview.png")).resolve()
WAIT = float(arg("--wait", "20"))
LOG = OUT.with_suffix(".log")
LOG.write_text("", encoding="utf-8")


def log(m):
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main_window():
    return bpy.context.window_manager.windows[0]


def view3d():
    for a in main_window().screen.areas:
        if a.type == "VIEW_3D":
            return a
    return None


_state = {"t": 0.0}


def tick():
    _state["t"] += 1.0
    t = _state["t"]
    area = view3d()
    if area is None:
        log("no VIEW_3D")
        bpy.ops.wm.quit_blender()
        return None
    if t == 1.0:
        # 3D ビューを窓いっぱいに、カメラ視点、レンダー表示 + コンポジタ
        win = main_window()
        region = next(r for r in area.regions if r.type == "WINDOW")
        with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
            bpy.ops.screen.screen_full_area()
        area = view3d()
        space = area.spaces[0]
        space.show_region_ui = False
        space.show_region_header = False
        space.overlay.show_overlays = False
        space.show_gizmo = False
        space.shading.type = "RENDERED"
        space.shading.use_compositor = "ALWAYS"
        space.shading.render_pass = "COMBINED"
        region = next(r for r in area.regions if r.type == "WINDOW")
        with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
            bpy.ops.view3d.view_camera()
            bpy.ops.view3d.view_center_camera()
        log(f"view set, area {area.width}x{area.height}")
        return 1.0
    if t < WAIT:
        return 1.0
    win = main_window()
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
        bpy.ops.screen.screenshot_area(filepath=str(OUT))
    log(f"shot {OUT} area {area.width}x{area.height}")
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=2.0)
