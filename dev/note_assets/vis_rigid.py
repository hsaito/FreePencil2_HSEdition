"""リグの付き方を色で見る: ボーン1本に固定された頂点=赤、関節で混ざる頂点=青、リグ無し=灰。
  blender -b --factory-startup --python vis_rigid.py -- --only heavy-zaku,man_01,anime-girl --out out/separation
"""
import sys
from pathlib import Path
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "separation"))).resolve()
ONLY = arg("--only", "heavy-zaku,man_01,anime-girl").split(",")
sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch
import make_demo_movie as dm, eval_style_all as esa, scan_models
esa.RES = 800
found = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT) if any(p in Path(m["path"]).stem for p in ONLY)]
for m in found:
    name = Path(m["path"]).stem[:16]
    meshes, _ = dm.load(m["path"])
    esa.stage(meshes)
    sc = bpy.context.scene
    sc.render.engine = fp_batch.eevee_engine()
    sc.render.resolution_x = sc.render.resolution_y = 800
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    n_r = n_b = 0
    for o in meshes:
        me = o.data
        at = me.color_attributes.get("rigidvis") or me.color_attributes.new("rigidvis", "FLOAT_COLOR", "POINT")
        arm = any(md.type == "ARMATURE" for md in o.modifiers) and len(o.vertex_groups) > 0
        for v in me.vertices:
            ws = [g.weight for g in v.groups if g.weight > 1e-4] if arm else []
            if not ws:
                c = (0.55, 0.55, 0.55, 1)
            elif max(ws) / sum(ws) > 0.99:
                c = (0.9, 0.1, 0.1, 1); n_r += 1
            else:
                c = (0.1, 0.35, 0.95, 1); n_b += 1
            at.data[v.index].color = c
    mat = bpy.data.materials.new("rigidvis")
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_type = "GEOMETRY"; a.attribute_name = "rigidvis"
    e = nt.nodes.new("ShaderNodeEmission"); o_ = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(a.outputs["Color"], e.inputs["Color"]); nt.links.new(e.outputs[0], o_.inputs["Surface"])
    for ob in meshes:
        for ms in ob.material_slots:
            ms.link = "OBJECT"; ms.material = mat
        if not ob.material_slots:
            ob.data.materials.append(mat)
    sc.render.use_compositing = False
    sc.render.filepath = str(OUT / f"{name}_rigid.png")
    bpy.ops.render.render(write_still=True)
    print(f"@@@ {name} red={n_r} blue={n_b} rigid={n_r/max(n_r+n_b,1):.2f}", flush=True)
