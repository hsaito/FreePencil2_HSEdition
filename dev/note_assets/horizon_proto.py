"""地平線の黒い帯の試作(アドオンは変えない。この場の group だけ差し替える)。

深度チャンネルは |Sobel(Z)| / (Z+0.5)。平らな地面では Z の勾配が奥ほど急になり、
地平線の手前が太い帯になる。1/Z は平面上で画面座標の一次式なので、
|Laplace(1/Z)| * (Z+0.5) は平面でちょうど 0、物の前後の段差では「深度が何割
変わったか」に比例する(Sobel の 4ΔZ/Z に対し Laplace は 3/8 ΔZ/Z -> 係数 G)。

  blender -b --factory-startup --python horizon_proto.py -- <out> <ground|noground> <PRECISE|WEIGHTED> G1,G2,...
"""
import math, sys
from pathlib import Path
ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
SCENE, STYLE = ARGV[1], ARGV[2]
GAINS = [float(g) for g in ARGV[3].split(",")] if len(ARGV) > 3 else []
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch
fp_batch.install_addon()

if SCENE.startswith("model:"):
    import glob
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    d = Path.home() / "blenderkit_data" / "models"
    src = sorted(Path(p) for p in glob.glob(str(d / (SCENE[6:].replace("+g", "") + "*") / "*.blend")))[0]
    meshes, others = fp_batch.append_objects(src)
    shapes = {pb.custom_shape.name for a in others if a.type == "ARMATURE" and a.pose
              for pb in a.pose.bones if pb.custom_shape is not None}
    for o in meshes:
        if o.name in shapes or o.name.lower().startswith(("cs_", "wgt", "shape_")):
            o.hide_render = True
    content = [o for o in meshes if not o.hide_render] or meshes
    cluster = fp_batch.dominant_cluster(content)
    for o in content:
        if o not in cluster:
            o.hide_render = True
    meshes = [o for o in content if o in cluster] or content
    fp_batch.normalize(meshes + others, meshes)
    sc.render.resolution_x = sc.render.resolution_y = 640
    fp_batch.setup_camera_and_light()
    if SCENE.endswith("+g"):
        bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, min((o.matrix_world @ __import__("mathutils").Vector(c)).z for o in meshes for c in o.bound_box)))
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 5
    SCENE = SCENE[6:].split("_")[0].replace("+g", "") + ("_g" if SCENE.endswith("+g") else "")
elif SCENE == "ground":
    bpy.ops.wm.open_mainfile(filepath=r"E:\10_cowork\00_code\22_FreePencil\dev\batch\out\audit\f452\base.blend")
else:
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add(size=1.8, location=(-1.1, 0, 0.9))
    bpy.context.object.modifiers.new("S", "SUBSURF"); bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
    bpy.ops.mesh.primitive_cube_add(size=0.7, location=(0.5, -0.8, 0.35))
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
    cam.location = (0, -6, 0.8); cam.rotation_euler = (math.radians(86), 0, 0)
    lt = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN")); sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(40), 0, math.radians(30))
    sc.render.resolution_x, sc.render.resolution_y = 480, 270
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 5
sc = bpy.context.scene
sc.render.film_transparent = True
ms = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
bpy.ops.object.select_all(action="DESELECT")
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
sc.fp_auto_style = STYLE
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
sc.render.film_transparent = True


def render(name):
    sc.render.filepath = str(OUT / f"{SCENE}_{STYLE}_{name}.png")
    bpy.ops.render.render(write_still=True)


render("now")
render("now2")
grp = next(g for g in bpy.data.node_groups if g.name.startswith("FreePencil_v1_1_0") and "DepthDenom" in g.nodes)
nd = grp.nodes
den, norm, sob = nd["DepthDenom"], nd["Normalize"], nd["Filter.001"]
img_in = sob.inputs.get("Image") or sob.inputs[1]
inv = nd.new("CompositorNodeMath" if bpy.app.version < (5, 0, 0) else "ShaderNodeMath"); inv.operation = "DIVIDE"; inv.inputs[0].default_value = 1.0
grp.links.new(den.outputs[0], inv.inputs[1])
grp.links.new(inv.outputs[0], img_in)
if bpy.app.version < (5, 0, 0):
    sob.filter_type = "LAPLACE"
else:
    sob.inputs["Type"].default_value = "Laplace"
ab = nd.new("CompositorNodeMath" if bpy.app.version < (5, 0, 0) else "ShaderNodeMath"); ab.operation = "ABSOLUTE"
grp.links.new(sob.outputs[0], ab.inputs[0])
gain = nd.new("CompositorNodeMath" if bpy.app.version < (5, 0, 0) else "ShaderNodeMath"); gain.operation = "MULTIPLY"
grp.links.new(ab.outputs[0], gain.inputs[0])
norm.operation = "MULTIPLY"
grp.links.new(gain.outputs[0], norm.inputs[0])
grp.links.new(den.outputs[0], norm.inputs[1])
for g in GAINS:
    gain.inputs[1].default_value = g
    render(f"lap{g:g}")
print("@@ done", SCENE, STYLE, flush=True)
import os
if os.environ.get("FP_SAVE"):
    gain.inputs[1].default_value = GAINS[-1] if GAINS else 11.0
    bpy.ops.wm.save_as_mainfile(filepath=os.environ["FP_SAVE"], copy=True)
