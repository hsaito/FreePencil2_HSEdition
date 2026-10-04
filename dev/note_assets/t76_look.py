import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()
OUT = Path(__file__).resolve().parent / "out" / "t76"; OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_homefile(use_empty=True)
objs = []
bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.2, 0, 0.9)); objs.append(bpy.context.object)
bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0.8, 0.3, 0.6)); objs.append(bpy.context.object)
for i in range(4):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.8, -0.31, 0.2 + i * 0.28)); g = bpy.context.object; g.scale = (1.0, 0.02, 0.03); objs.append(g)
sc = bpy.context.scene
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -6, 1.6); cam.rotation_euler = (math.radians(82), 0, 0)
sc.render.resolution_x, sc.render.resolution_y = 320, 240
sc.render.film_transparent = True
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"): setattr(sc, p_, False)
sc.fp_color_seed = 7; sc.fp_auto_style = "WEIGHTED"
bpy.ops.object.select_all(action="DESELECT")
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
for ft in (True, False):
    sc.render.film_transparent = ft
    sc.render.filepath = str(OUT / f"ft{int(ft)}.png"); bpy.ops.render.render(write_still=True)
import importlib
compat = importlib.import_module(next(m for m in sys.modules if m.endswith("freepencil2.compat")))
tree = compat.get_compositor_tree(sc)
rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
for s in rl.outputs:
    for l in s.links:
        print("@@", s.name, "->", l.to_node.bl_idname, l.to_node.label, l.to_socket.name, flush=True)
lw = importlib.import_module(next(m for m in sys.modules if m.endswith("freepencil2.line_weight")))
import tempfile, numpy as np
sil = next(l.to_node for l in rl.outputs["Alpha"].links if l.to_node.bl_idname.endswith("Math") and l.to_node.operation == "MULTIPLY")
lt = next(l.to_node for l in rl.outputs["Depth"].links if l.to_node.bl_idname.endswith("Math"))
fo = tree.nodes.new("CompositorNodeOutputFile"); compat.file_output_clear_slots(fo)
for slot in ("sil", "near", "dep"):
    compat.file_output_add_slot(fo, slot, "OPEN_EXR", "RGB")
tree.links.new(sil.outputs[0], fo.inputs["sil"]); tree.links.new(lt.outputs[0], fo.inputs["near"])
tree.links.new(rl.outputs["Depth"], fo.inputs["dep"])
for ft in (True, False):
    sc.render.film_transparent = ft
    tmp = tempfile.mkdtemp(); compat.file_output_set_dir(fo, tmp)
    bpy.ops.render.render()
    for slot in ("sil", "near", "dep"):
        a = lw._load_float(lw._find(tmp, slot)); h, w = a.shape
        print(f"@@ ft={ft} {slot}: bg={a[5,5]:.4g} obj={a[h//2, w//4]:.4g} mean={a.mean():.4f}", flush=True)
print("@@ clip_end", sc.camera.data.clip_end)
tree.nodes.remove(fo)
grp = next(n for n in tree.nodes if n.type == "GROUP" and n.node_tree and n.node_tree.name.startswith("FreePencil_v1_1_0_"))
for l in list(grp.inputs["Alpha"].links): tree.links.remove(l)
tree.links.new(sil.outputs[0], grp.inputs["Alpha"])
for ft in (True, False):
    sc.render.film_transparent = ft
    sc.render.filepath = str(OUT / f"grpsil_ft{int(ft)}.png"); bpy.ops.render.render(write_still=True)
print("@@ grp done")
