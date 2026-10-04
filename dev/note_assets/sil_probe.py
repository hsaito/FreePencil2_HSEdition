"""手描き背景・地面なし・背景透過で、gap_fill に渡すシルエットとレンダーのアルファを画像で出す。"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()
OUT = Path(__file__).resolve().parent / "out" / "silprobe"; OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_monkey_add(size=1.8, location=(-1.1, 0, 0.9))
bpy.context.object.modifiers.new("S", "SUBSURF"); bpy.ops.object.shade_smooth()
bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -6, 0.8); cam.rotation_euler = (math.radians(86), 0, 0)
lt = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN")); sc.collection.objects.link(lt)
lt.rotation_euler = (math.radians(40), 0, math.radians(30))
sc.render.resolution_x, sc.render.resolution_y = 480, 270
sc.render.film_transparent = True
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    setattr(sc, p_, False)
sc.fp_color_seed = 5
ms = [o for o in sc.objects if o.type == "MESH"]
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
sc.fp_auto_style = "BACKGROUND"
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
sc.render.film_transparent = True
tree = sc.node_tree if hasattr(sc, "node_tree") and sc.node_tree else sc.compositing_node_group
comp = next(n for n in tree.nodes if n.type == "COMPOSITE")
rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
# gap_fill のシルエット = MULTIPLY で、入力 0 がレンダーの Alpha のもの
sils = [n for n in tree.nodes if n.type == "MATH" and n.operation == "MULTIPLY" and n.inputs[0].is_linked
        and n.inputs[0].links[0].from_socket == rl.outputs["Alpha"]]
print("@@ sil nodes", [(n.name, n.label) for n in sils])
keep = comp.inputs[0].links[0].from_socket
sc.render.film_transparent = True
for nm, sock in [("alpha", rl.outputs["Alpha"])] + [(f"sil{i}", n.outputs[0]) for i, n in enumerate(sils)] + [("depth", rl.outputs.get("Depth"))]:
    if sock is None: continue
    if nm == "depth":
        m = tree.nodes.new("CompositorNodeMath"); m.operation = "LESS_THAN"; m.inputs[1].default_value = 1000*0.999 if bpy.app.version < (5,0,0) else 65000
        tree.links.new(sock, m.inputs[0]); sock = m.outputs[0]
    tree.links.new(sock, comp.inputs[0])
    sc.render.filepath = str(OUT / f"{nm}.png"); bpy.ops.render.render(write_still=True)
