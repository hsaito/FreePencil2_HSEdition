"""塗り分けの色が十分多様に出ているかを、目で見るためのレンダを作る。

数値では判定しない(CLAUDE.md の憲法)。各モデルについて2枚描く。

  *_vc.png    頂点カラーを Attribute -> Emission で素通し = 塗り分けそのもの
  *_line.png  同じ状態で線画パイプラインを通した結果

.blend も残すので、ユーザーが自分で開いて確かめられる。

    blender -b --factory-startup --python eval_palette.py -- [--tag now]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


TAG = arg("--tag", "now")
OUT = Path(arg("--out", str(HERE / "out" / "palette" / TAG))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
AUTO = "--manual" not in ARGV
DEG = float(arg("--deg", "20.0"))
T0 = time.time()

TARGETS = [
    ("suzanne", "SUZANNE", 0),
    ("suzanne_subsurf2", "SUZANNE", 2),
    ("text_Text", "TEXT", "Text"),
    ("text_FreePencil2", "TEXT", "FreePencil2"),
    ("053_kaino", "MODEL", None),
    ("004_anime-girl", "MODEL", None),
    ("006_audi", "MODEL", None),
    ("010_baseball", "MODEL", None),
    ("032_dutch", "MODEL", None),
]


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def make_text(body):
    cur = bpy.data.curves.new("T", type="FONT")
    cur.body = body
    cur.extrude = 0.12
    cur.bevel_depth = 0.01
    cur.bevel_resolution = 0
    cur.resolution_u = 12
    o = bpy.data.objects.new("TXT", cur)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    return [bpy.context.object]


def make_suzanne(levels):
    """スザンヌ。levels>0 でサブサーフを適用する。

    サブサーフ2のスザンヌは、自動しきい値が網目状に砕く典型例だった
    (2048島)。過剰分割の対応がここから始まっているので必ず見る。
    """
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    if levels > 0:
        m = o.modifiers.new("Subsurf", type="SUBSURF")
        m.levels = m.render_levels = levels
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
    return [o]


def fit_camera(meshes):
    # append 直後は matrix_world が未評価で、寸法を取り違えて被写体が
    # 米粒になる。必ず評価してから測る
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    ctr = (mn + mx) * 0.5
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 1e-4)
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 50.0
    cd.clip_end = size * 40
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    d = Vector((0.75, -1.0, 0.45)).normalized()
    cam.location = ctr + d * (size * 2.0)
    v = ctr - cam.location
    cam.rotation_euler = v.to_track_quat("-Z", "Y").to_euler()
    lt = bpy.data.lights.new("L", type="AREA")
    lt.energy = size * size * 700.0
    lt.size = size * 2.0
    lo = bpy.data.objects.new("L", lt)
    bpy.context.scene.collection.objects.link(lo)
    lo.location = ctr + Vector((0.4, -0.8, 1.4)) * size
    lo.rotation_euler = (math.radians(35), 0.0, math.radians(25))


def render_vc(scene, png):
    mat = bpy.data.materials.new("VC")
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


def n_colors(meshes):
    """使われている色の数。判定には使わない。画像の見出し用の目安"""
    keys = set()
    for o in meshes:
        ca = o.data.color_attributes.active_color
        if ca is None:
            continue
        n = len(o.data.loops) if ca.domain == 'CORNER' else len(o.data.vertices)
        buf = np.zeros(n * 4, dtype=np.float32)
        ca.data.foreach_get("color", buf)
        c = np.round(buf.reshape(n, 4)[:, :3] * 255).astype(np.int64)
        keys |= set(np.unique(c[:, 0] * 65536 + c[:, 1] * 256 + c[:, 2]).tolist())
    return len(keys)


def one(name, kind, body, models):
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    if kind == "TEXT":
        meshes = make_text(body)
    elif kind == "SUZANNE":
        meshes = make_suzanne(body)
    else:
        m = next((x for x in models if x["name"].startswith(name)), None)
        if m is None:
            say(f"{name}: 見つからない")
            return None
        meshes, _o = fp_batch.append_objects(Path(m["path"]))
        if not meshes:
            return None
    # HEAD には fp_preview_mode がまだ無い。変更前後を同じスクリプトで
    # 撮れるよう、無い設定は黙って飛ばす
    def setp(name, value):
        if hasattr(scene, name):
            setattr(scene, name, value)

    setp("fp_use_random_seed", False)
    setp("fp_color_seed", 42)
    setp("fp_enable_compositor_view", False)
    setp("fp_auto_detect_aov", False)
    setp("fp_preview_mode", 'NONE')
    setp("fp_white_preview", False)
    setp("fp_auto_supersample", False)
    setp("fp_supersample", False)
    scene.fp_sharp_auto = AUTO
    if not AUTO:
        scene.fp_sharp_edges = DEG

    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    fit_camera(meshes)
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    line_png = OUT / f"{name}_line.png"
    fp_batch.render_still(scene, line_png, 1)
    vc_png = OUT / f"{name}_vc.png"
    render_vc(scene, vc_png)
    blend = OUT / f"{name}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    nc = n_colors(meshes)
    say(f"{name:<22} 色数={nc:>5}  -> {vc_png.name} / {line_png.name}")
    return {"name": name, "colors": nc,
            "vc": vc_png.name, "line": line_png.name}


def main():
    fp_batch.install_addon()
    models = scan_models.scan(scan_models.DEFAULT_ROOT)
    rows = []
    for name, kind, body in TARGETS:
        try:
            r = one(name, kind, body, models)
        except Exception as e:                      # noqa: BLE001
            say(f"{name}: 失敗 {e}")
            continue
        if r:
            rows.append(r)
    (OUT / "index.json").write_text(
        json.dumps({"tag": TAG, "auto": AUTO, "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
