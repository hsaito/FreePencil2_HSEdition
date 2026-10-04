"""操作の流れを見せる動画のための、UI 状態を順に撮る (GUI)。

本物の画面録画ではない。Blender の画面を外から録る手段がこの環境に
無いので、UI の状態を1枚ずつ撮って、あとで連番に組み立てる。
マウスカーソルは写らないので、合成の側で描き足す。

撮るのは 3D ビューのエリア丸ごと (サイドバーを含む)。

  m0_closed        サイドバーを閉じた状態
  m1_sidebar       N キーでサイドバーを出し、FreePencil タブ・STEP0 を開く
  m2_done          全自動セットアップを実行したあと
  m3_step3         STEP3 を開く (線の感度 0.5)
  m4_sens100       線の感度 1.0 (v2.6 までの既定)
  m5_sens035       線の感度 0.35
  m6_sens050       0.5 に戻す

使い方 (ui_shots.py と同じ):
  blender --factory-startup -p 0 0 2400 1400 <prepared.blend> \
      --python ui_movie.py -- --out <絶対パス>

--out は必ず絶対パスにすること。相対だと bpy 側が別の場所に解決して
しまい、ログだけ残って画像が出ない。
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ADDON_MODULE = "bl_ext.user_default.freepencil2"

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1]) if "--out" in ARGV else Path.cwd()
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ui_movie.log"
LOG.write_text("", encoding="utf-8")

PANEL_ORDER = ["FREEPENCIL_PT_STEP0", "FREEPENCIL_PT_STEP1",
               "FREEPENCIL_PT_STEP2", "FREEPENCIL_PT_STEP3",
               "FREEPENCIL_PT_STEP4", "FREEPENCIL_PT_CAMERAS"]
_current: dict[str, type] = {}
_originals: dict[str, type] = {}
_variant = {"n": 0}


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def win():
    return bpy.context.window_manager.windows[0]


def view3d():
    for area in win().screen.areas:
        if area.ui_type == "VIEW_3D":
            return area
    return None


def shoot(name: str) -> None:
    area = view3d()
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    with bpy.context.temp_override(window=win(), screen=win().screen,
                                   area=area, region=region):
        bpy.ops.screen.screenshot_area(filepath=str(OUT / name))
    log(f"shot {name} {area.width}x{area.height}")


def panels_variant(open_ids: set[str]) -> None:
    """パネルの開閉。描画済みの idname には効かないので別名で登録し直す。"""
    for cls in _current.values():
        bpy.utils.unregister_class(cls)
    _variant["n"] += 1
    suffix = f"_M{_variant['n']}"
    for idname in PANEL_ORDER:
        base = _originals[idname]
        new = type(base.__name__ + suffix, (base,),
                   {"bl_idname": idname + suffix,
                    "bl_options": set() if idname in open_ids
                    else {"DEFAULT_CLOSED"}})
        bpy.utils.register_class(new)
        _current[idname] = new


def closed():
    """サイドバーを閉じ、カメラ視点に合わせる。

    view_all() だとシーン全体に引いてモデルが豆粒になる。動画では
    「これから線を出す対象」が大きく見えていないと意味がないので、
    レンダリングと同じ画角=カメラ視点にする。
    """
    area = view3d()
    space = area.spaces.active
    space.show_region_ui = False
    space.shading.type = "SOLID"
    space.overlay.show_overlays = False
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    # このシーンにはカメラが無い。view_all() だとシーン全体に引いて
    # モデルが豆粒になるので、メッシュを選択して view_selected で寄せる。
    # オーバーレイは切ってあるので選択の橙色の輪郭は出ない
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in meshes:
        o.select_set(True)
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    with bpy.context.temp_override(window=win(), screen=win().screen,
                                   area=area, region=region):
        if meshes:
            bpy.ops.view3d.view_selected()
            log(f"view_selected on {len(meshes)} meshes")
        else:
            bpy.ops.view3d.view_all()
            log("no mesh: view_all")


def open_sidebar():
    """N キーでサイドバーを出すところまで。タブ切り替えは次のティック。

    描画されていないリージョンの active_panel_category は読み取り専用で、
    同じティックで書こうとすると失敗する。
    """
    view3d().spaces.active.show_region_ui = True
    panels_variant({"FREEPENCIL_PT_STEP0"})


def select_tab():
    for r in view3d().regions:
        if r.type == "UI":
            try:
                r.active_panel_category = "FreePencil"
                log("tab -> FreePencil")
            except Exception as exc:                    # noqa: BLE001
                log(f"tab switch failed: {exc}")


def run_setup():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in meshes:
        o.select_set(True)
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc = bpy.context.scene
    log(f"auto_setup done  sensitivity={sc.fp_line_sensitivity}")


def step3():
    panels_variant({"FREEPENCIL_PT_STEP3"})


def sens(value: float):
    def f():
        bpy.context.scene.fp_line_sensitivity = value
        log(f"sensitivity -> {bpy.context.scene.fp_line_sensitivity}")
    return f


STEPS = [
    # 1枚目は捨てる。ui_shots.py と同じで、最初の1枚はフレームバッファが
    # まだ描かれておらず真っ黒になることがある
    (closed, "_warm.png"),
    (closed, "m0_closed.png"),
    (open_sidebar, "m1_open.png"),
    (select_tab, "m2_tab.png"),
    (run_setup, "m3_done.png"),
    (step3, "m4_step3.png"),
    (sens(1.0), "m5_sens100.png"),
    (sens(0.35), "m6_sens035.png"),
    (sens(0.5), "m7_sens050.png"),
]

_state = {"i": 0, "phase": "prep"}


def tick():
    try:
        if _state["i"] >= len(STEPS):
            log("done")
            bpy.ops.wm.quit_blender()
            return None
        prep, name = STEPS[_state["i"]]
        if _state["phase"] == "prep":
            log(f"prep {name}")
            prep()
            for a in win().screen.areas:
                a.tag_redraw()
            _state["phase"] = "shoot"
            # コンポジタのプレビューは反映に時間がかかる。長めに待つ
            return 1.6
        shoot(name)
        _state["i"] += 1
        _state["phase"] = "prep"
        return 0.6
    except Exception:
        import traceback
        log("ERROR\n" + traceback.format_exc())
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
    bpy.app.timers.register(tick, first_interval=1.5)
    log("timer registered")
except Exception:
    import traceback
    log("SETUP ERROR\n" + traceback.format_exc())
