"""sample.blend で、しきい値の決め方を見比べる。

シーンのカメラ・ライトはそのまま使う。塗り分けだけを変えて撮る。

  auto    いまの自動しきい値
  cut5    5度で切る(ぼかし無し) = 切りすぎの状態
  smooth  5度で切る + 鋭角以外を溶かす(提案の方式)

判定は画像で行う。.blend も条件ごとに保存する。

    blender -b --factory-startup --python eval_sample.py -- [--blur 20]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


SRC = Path(arg("--src", r"E:\10_cowork\00_code\22_FreePencil\sample\sample.blend"))
OUT = Path(arg("--out", str(HERE / "out" / "sample"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
BLUR = int(arg("--blur", "20"))
KEEP = float(arg("--keep", "25.0"))
CUT = float(arg("--cut", "5.0"))
RES = int(arg("--res", "1280"))
T0 = time.time()

MODES = [
    ("a60", "自動(60度相当)", 60.0, 0),
    ("m50", "手動50度", 50.0, 0),
    ("m40", "手動40度", 40.0, 0),
    ("m35", "手動35度", 35.0, 0),
    ("m30", "手動30度", 30.0, 0),
    ("m25", "手動25度", 25.0, 0),
]


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def render_vc(scene, png):
    """頂点カラーを素通しで描く。"""
    mat = bpy.data.materials.new("FP_DEBUG_VC")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "mecha_color"
    em = nt.nodes.new("ShaderNodeEmission")
    ou = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
    saved = {}
    for o in scene.objects:
        if o.type != "MESH":
            continue
        saved[o.name] = [s.material for s in o.material_slots]
        if not o.material_slots:
            o.data.materials.append(mat)
        else:
            for s in o.material_slots:
                s.material = mat
    kc = scene.use_nodes
    kv = scene.view_settings.view_transform
    scene.use_nodes = False
    scene.view_settings.view_transform = 'Standard'
    fp_batch.render_still(scene, png, 1)
    scene.use_nodes = kc
    scene.view_settings.view_transform = kv
    for o in scene.objects:
        if o.type == "MESH" and o.name in saved:
            for s, m in zip(o.material_slots, saved[o.name]):
                s.material = m


def one(key, label, cut, blur):
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == 'MESH']

    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False
    # STEP0 のおすすめ設定が fp_sharp_auto を True に戻すので切る
    scene.fp_auto_sharp = False
    scene.fp_sharp_auto = (cut is None)
    if cut is not None:
        scene.fp_sharp_edges = cut
    scene.fp_curve_blur = blur
    scene.fp_curve_blur_angle = KEEP
    # auto 行だけ「自動が決める回数」を見たいので、それ以外は明示した回数を使う


    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 32
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = RES
    scene.render.resolution_y = int(RES * 9 / 16)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    fp_batch.render_still(scene, OUT / f"{key}_line.png", 1)
    render_vc(scene, OUT / f"{key}_vc.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{key}.blend"))
    say(f"{label}")


def main():
    fp_batch.install_addon()
    for key, label, cut, blur in MODES:
        one(key, label, cut, blur)
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
