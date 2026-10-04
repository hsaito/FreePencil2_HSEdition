"""初期版の「シャープを打つ前処理」を再現して、サブディビジョンとの相性を見る。

初期版(14e1db6 operators/vertex_color.py)はこうしていた。

    bpy.ops.mesh.edges_select_sharp(sharpness=line_edges)
    bpy.ops.mesh.mark_sharp(clear=False)

角度で辺を選んでメッシュに実際のシャープを打ち、塗り分けはそのシャープを
見て島を切る。角度は「シャープを打つための道具」であって、島を切る基準
そのものではなかった。

いまの mark_boundaries はシャープを常に境界として扱う(clear_sharps=False の
とき ok &= ~self.sharp)ので、**しきい値を 179 度にすれば角度では切れず、
境界はシャープだけ**になる。これで初期版と同じ切り方を再現できる。

見たいのは「サブディビジョンが生きているとき、打ったシャープが
レンダリングで角として残るのか」。残るなら誤判定は原理的に起きない。

    blender -b --factory-startup --python eval_legacy_sharp.py -- [--deg 30]
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


SRC = Path(arg("--src", r"E:\10_cowork\00_code\22_FreePencil\sample\sample.blend"))
OUT = Path(arg("--out", str(HERE / "out" / "legacy_sharp"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
DEG = float(arg("--deg", "30.0"))
RES = int(arg("--res", "1280"))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def mark_sharp_by_angle(obj, deg):
    """初期版と同じ手順でシャープを打つ。"""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.reveal()
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.mark_sharp(clear=True)
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.edges_select_sharp(sharpness=math.radians(deg))
    bpy.ops.mesh.mark_sharp(clear=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    ne = len(obj.data.edges)
    s = np.zeros(ne, dtype=bool)
    obj.data.edges.foreach_get("use_edge_sharp", s)
    return int(s.sum()), ne


def render_vc(scene, png):
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


def one(key, legacy):
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
    scene.fp_auto_sharp = False
    scene.fp_curve_blur = 0
    scene.fp_curve_blur_auto = False

    if legacy:
        # 初期版の再現: 先にシャープを打ち、島はシャープだけで切る
        for o in meshes:
            n, ne = mark_sharp_by_angle(o, DEG)
            say(f"  {o.name:<14} シャープ {n:,}/{ne:,}本")
        scene.fp_sharp_auto = False
        scene.fp_sharp_edges = 179.0   # 角度では切らせない
        scene.fp_sharp_clear = False   # 打ったシャープを尊重する
    else:
        scene.fp_sharp_auto = True

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
    say(f"{key} 完了")


def main():
    fp_batch.install_addon()
    one("now", legacy=False)
    one("legacy", legacy=True)
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
