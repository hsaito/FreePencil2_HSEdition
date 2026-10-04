"""町の 1 フレームで、塗り分け(頂点カラー)を Attribute -> Emission で素通しに撮る。

線が出ない所の原因が「塗り分けの色が同じ」なのか「検出で消えている」の
かを、目で見て切り分けるため。コンポジタは切る。

  blender -b --factory-startup --python look_vcol.py -- --frame 560 \
      [--attrs mecha_color,fine_color] [--out out/town_v2/vcol]
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
FRAME = int(arg("--frame", "560"))
ATTRS = arg("--attrs", "mecha_color,fine_color").split(",")
OUT = Path(arg("--out", str(HERE / "out" / "town_v2" / "vcol"))).resolve()
BLEND = Path(arg("--blend", str(HERE / "out" / "town_v2" / "town.blend"))).resolve()

sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import shoot_town_v2 as st        # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)


def emission_material(attr):
    m = bpy.data.materials.new(f"look_{attr}")
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
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    st.FRAMES = 720
    st.moving_cars(sc)
    st.aim(sc.camera, FRAME)
    sc.frame_set(FRAME + 1)
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.resolution_percentage = 50
    sc.eevee.taa_render_samples = 1          # 色の境目をぼかさない
    sc.render.film_transparent = False
    sc.world = sc.world or bpy.data.worlds.new("W")
    sc.render.use_compositing = False
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    # view_layer.material_override は EEVEE で効かなかった(普通の灰色の
    # 陰影のまま撮れた)。スロットの材質を直接差し替える
    meshes = [o for o in sc.objects if o.type == "MESH"]
    for attr in ATTRS:
        mat = emission_material(attr)
        for o in meshes:
            if not o.material_slots:
                o.data.materials.append(mat)
            for ms in o.material_slots:
                ms.link = "OBJECT"
                ms.material = mat
        sc.render.filepath = str(OUT / f"f{FRAME:04d}_{attr}.png")
        bpy.ops.render.render(write_still=True)
        print(f"@@@ {attr}", flush=True)


if __name__ == "__main__":
    main()
