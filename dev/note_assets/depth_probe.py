"""背景と物の上で、Depth / Alpha / AO が何になるかを、背景の透過あり/なしで読む。"""
import math, sys, tempfile, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()
compat = importlib.import_module(next(m for m in sys.modules if m.endswith("freepencil2.compat")))
lw = importlib.import_module(next(m for m in sys.modules if m.endswith("freepencil2.line_weight")))
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_monkey_add(size=2)
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -6, 0.4); cam.rotation_euler = (math.radians(86), 0, 0)
sc.render.resolution_x, sc.render.resolution_y = 160, 120
vl = sc.view_layers[0]; vl.use_pass_z = True; vl.use_pass_ambient_occlusion = True
tree = compat.get_compositor_tree(sc, create=True)
for n in list(tree.nodes): tree.nodes.remove(n)
rl = tree.nodes.new("CompositorNodeRLayers")
fo = tree.nodes.new("CompositorNodeOutputFile")
compat.file_output_clear_slots(fo)
names = {"Depth": "dep", "Alpha": "alp", "AO": "aoo"}
for s, slot in names.items():
    compat.file_output_add_slot(fo, slot, "OPEN_EXR", "RGB")
for s, slot in names.items():
    src = rl.outputs.get(s) or (compat.render_layer_socket(rl, compat.AO_SOCKETS) if s == "AO" else None)
    tree.links.new(src, fo.inputs[slot])
for ft in (False, True):
    sc.render.film_transparent = ft
    tmp = tempfile.mkdtemp(prefix="dp_")
    compat.file_output_set_dir(fo, tmp)
    bpy.ops.render.render()
    for s, slot in names.items():
        a = lw._load_float(lw._find(tmp, slot))
        h, w = a.shape
        print(f"@@ {bpy.app.version_string[:3]} film_transparent={ft} {s:6s} bg={a[h-3,3]:.4g}  model={a[h//2,w//2]:.4g}", flush=True)
