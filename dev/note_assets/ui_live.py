"""画面キャプチャに向けて、Blender の UI を実時間で操作する (GUI)。

ui_movie.py は状態を1枚ずつ撮ったが、こちらは capture_screen.py に
録らせる前提で、実際の時間の流れの中で操作を進める。進捗バーや
ポップアップの出方も、そのまま録画に入る。

各操作の時刻を steps.json に書き出す。あとで字幕を合わせるために使う。

  blender --factory-startup -p 2560 0 1920 1080 <prepared.blend> \
      --python ui_live.py -- --out <絶対パス>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy

ADDON_MODULE = "bl_ext.user_default.freepencil2"

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1]) if "--out" in ARGV else Path.cwd()
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ui_live.log"
LOG.write_text("", encoding="utf-8")
MARKS: list[dict] = []

PANEL_ORDER = ["FREEPENCIL_PT_STEP0", "FREEPENCIL_PT_STEP1",
               "FREEPENCIL_PT_STEP2", "FREEPENCIL_PT_STEP3",
               "FREEPENCIL_PT_STEP4", "FREEPENCIL_PT_CAMERAS"]
_current: dict[str, type] = {}
_originals: dict[str, type] = {}
_variant = {"n": 0}


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.time():.3f} {msg}\n")


def mark(label: str) -> None:
    """字幕を出したい時刻に印を打つ。"""
    MARKS.append({"t": time.time(), "label": label})
    log(f"MARK {label}")


def win():
    return bpy.context.window_manager.windows[0]


def view3d():
    for area in win().screen.areas:
        if area.ui_type == "VIEW_3D":
            return area
    return None


def panels_variant(open_ids: set[str]) -> None:
    for cls in _current.values():
        bpy.utils.unregister_class(cls)
    _variant["n"] += 1
    suffix = f"_L{_variant['n']}"
    for idname in PANEL_ORDER:
        base = _originals[idname]
        new = type(base.__name__ + suffix, (base,),
                   {"bl_idname": idname + suffix,
                    "bl_options": set() if idname in open_ids
                    else {"DEFAULT_CLOSED"}})
        bpy.utils.register_class(new)
        _current[idname] = new


def prepare():
    area = view3d()
    space = area.spaces.active
    space.show_region_ui = False
    space.shading.type = "SOLID"
    space.overlay.show_overlays = False
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in meshes:
        o.select_set(True)
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    with bpy.context.temp_override(window=win(), screen=win().screen,
                                   area=area, region=region):
        bpy.ops.view3d.view_selected()
    mark("open")


def open_sidebar():
    view3d().spaces.active.show_region_ui = True
    panels_variant({"FREEPENCIL_PT_STEP0"})
    mark("sidebar")


def select_tab():
    for r in view3d().regions:
        if r.type == "UI":
            try:
                r.active_panel_category = "FreePencil"
            except Exception as exc:                    # noqa: BLE001
                log(f"tab switch failed: {exc}")
    mark("tab")


def run_setup():
    mark("run")
    # INVOKE_DEFAULT だとモーダルで走り、進捗バーが出たまま画面が
    # 動き続ける。タイマーからだと戻ってこないことがあるので、
    # 走ったかどうかは返り値で見て、駄目なら同期実行に落とす
    try:
        r = bpy.ops.freepencil.auto_setup("INVOKE_DEFAULT")
    except Exception as exc:                            # noqa: BLE001
        log(f"invoke failed: {exc}")
        r = {"CANCELLED"}
    log(f"auto_setup invoke -> {r}")
    if "RUNNING_MODAL" not in r and "FINISHED" not in r:
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        log("fallback EXEC_DEFAULT")


def wait_done():
    """セットアップが終わるまで待つ。ノードグループが出来たら完了とみなす。"""
    if any(g.name.startswith("FreePencil") for g in bpy.data.node_groups):
        mark("done")
        return True
    return False


def step3():
    panels_variant({"FREEPENCIL_PT_STEP3"})
    mark("step3")


def sweep(a: float, b: float, label: str):
    """感度をなめらかに動かす。1ティックで1段ずつ進める。"""
    state = {"i": 0}
    n = 14

    def f():
        if state["i"] == 0:
            mark(label)
        t = state["i"] / n
        bpy.context.scene.fp_line_sensitivity = a + (b - a) * t
        state["i"] += 1
        return state["i"] > n
    return f


# (関数, 何秒待つか, 完了を待つか) の並び
SEQ = [
    (prepare, 2.5, False),
    (open_sidebar, 1.4, False),
    (select_tab, 2.2, False),
    (run_setup, 0.2, False),
    (wait_done, 0.4, True),
    (None, 3.4, False),
    (step3, 2.0, False),
    (sweep(0.5, 1.0, "up"), 0.14, True),
    (None, 2.0, False),
    (sweep(1.0, 0.35, "down"), 0.14, True),
    (None, 2.0, False),
    (sweep(0.35, 0.5, "back"), 0.14, True),
    (None, 3.0, False),
]

_i = {"n": 0}


def announce():
    """自分のウィンドウ位置を書き出す。録画側はこれを見て範囲を決める。

    座標を人が決め打ちにすると、別のディスプレイを録ってしまう。
    実際に一度それをやって、無関係な画面を録画した。
    """
    w = win()
    (OUT / "ready.json").write_text(json.dumps(
        {"x": w.x, "y": w.y, "width": w.width, "height": w.height}),
        encoding="utf-8")
    log(f"window rect {w.x},{w.y} {w.width}x{w.height}")


def tick():
    try:
        # 録画側の準備ができるまで動かない
        if not (OUT / "go.txt").exists():
            return 0.25
        if _i["n"] >= len(SEQ):
            (OUT / "steps.json").write_text(
                json.dumps(MARKS, ensure_ascii=False), encoding="utf-8")
            log("done")
            bpy.ops.wm.quit_blender()
            return None
        fn, wait, repeat = SEQ[_i["n"]]
        if fn is None:
            _i["n"] += 1
            return wait
        ok = fn()
        if repeat and not ok:
            return wait                 # 同じ段をもう一度
        _i["n"] += 1
        for a in win().screen.areas:
            a.tag_redraw()
        return wait
    except Exception:
        import traceback
        log("ERROR\n" + traceback.format_exc())
        (OUT / "steps.json").write_text(
            json.dumps(MARKS, ensure_ascii=False), encoding="utf-8")
        bpy.ops.wm.quit_blender()
        return None


try:
    log("start " + bpy.data.filepath)
    log("addon_enable: " + str(
        bpy.ops.preferences.addon_enable(module=ADDON_MODULE)))
    view = bpy.context.preferences.view
    view.language = "ja_JP"
    view.use_translate_interface = True
    view.use_translate_tooltips = True
    view.ui_scale = 1.25
    _originals.update({n: getattr(bpy.types, n) for n in PANEL_ORDER})
    _current.update(_originals)
    announce()
    bpy.app.timers.register(tick, first_interval=0.5)
    log("timer registered")
except Exception:
    import traceback
    log("SETUP ERROR\n" + traceback.format_exc())
