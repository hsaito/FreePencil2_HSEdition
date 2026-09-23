"""人形の胸元のゴミの出どころを切り分ける。

テスト場(test_humans.py の保存)を開き、手前の人形の胸にカメラを寄せて、
線の出どころを1つずつ止めて撮る。塗り分けそのものも素通しで撮る。

  blender -b --factory-startup --python eval_chest_blob.py -- \
      [--blend out/humans/bg_off/humans.blend] [--out out/humans/blob]
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "humans" / "bg_off" / "humans.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "humans" / "blob"))).resolve()
FRAME = int(arg("--frame", "7"))

sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402


def emission(attr):
    m = bpy.data.materials.new("look_" + attr)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = "GEOMETRY"
    a.attribute_name = attr
    e = nt.nodes.new("ShaderNodeEmission")
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(a.outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
    return m


def main():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    sc.frame_set(FRAME)
    # 手前の人形(x=-1.5, y=5)の胸へ寄る
    grp = min((o for o in sc.objects if o.name.startswith("man_grp")),
              key=lambda o: o.matrix_world.translation.y)
    t = grp.matrix_world.translation
    tgt = Vector((t.x, t.y, 1.35))
    cam = sc.camera
    cam.location = tgt + Vector((0.35, -2.2, 0.15))
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 50
    sc.render.resolution_x, sc.render.resolution_y = 800, 800
    sc.eevee.taa_render_samples = 8

    def shot(tag):
        fp_batch.render_still(sc, OUT / f"{tag}.png", 1)
        print(f"@@@ {tag}", flush=True)

    base = {"fp_ch_bone": sc.fp_ch_bone, "fp_ch_mecha": sc.fp_ch_mecha,
            "fp_fine_lines": sc.fp_fine_lines}
    shot("all")
    sc.fp_ch_bone = 0.0
    shot("no_bone")
    sc.fp_ch_bone = base["fp_ch_bone"]
    sc.fp_ch_mecha = 0.0
    shot("no_mecha")
    sc.fp_ch_mecha = base["fp_ch_mecha"]
    sc.fp_fine_lines = 0.0
    shot("no_fine")
    sc.fp_fine_lines = base["fp_fine_lines"]
    sc.fp_line_weight = False
    bpy.ops.freepencil2.link_button()
    shot("no_weight")
    # 塗り分けの素通し
    body = [o for o in grp.children_recursive if o.type == "MESH"]
    sc.render.use_compositing = False
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.eevee.taa_render_samples = 1
    for attr in ("mecha_color", "fine_color", "bone_color"):
        mat = emission(attr)
        for o in body:
            for ms in o.material_slots:
                ms.link = "OBJECT"
                ms.material = mat
        shot("vcol_" + attr)
    print("@@@ done", flush=True)


if __name__ == "__main__":
    main()
