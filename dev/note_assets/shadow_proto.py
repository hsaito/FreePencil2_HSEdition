"""v2.9 の試作: 影の境界に色の線(影線)と、影のベタ。アドオンには入れず、STEP0 の後に
コンポジタへノードを足して絵を見る。

  blender -b --python shadow_proto.py -- <out_dir> [--model <blend>] [--res 900]
        [--style WEIGHTED] [--thr 0.35] [--color 0.15,0.35,0.85] [--width 1]

出す絵:
  a_step0.png       STEP0 だけ
  b_mask.png        影の白黒(直接光をしきい値で切ったもの)
  c_shadowline.png  影の境界に色の線
  d_line_fill.png   色の線 + 影のベタ(薄い灰)
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


MODEL = arg("--model", str(Path.home() / "blenderkit_data/models/anime-girl_0b0fdfcc-1359-466e-9d59-9e1c871c2f0b/anime-girl_2K_ba351a95-8237-43e1-8a6f-e36200f0e444.blend"))
RES = int(arg("--res", "900"))
STYLE = arg("--style", "WEIGHTED")
THR = float(arg("--thr", "0.35"))
COLOR = tuple(float(c) for c in arg("--color", "0.15,0.35,0.85").split(","))
WIDTH = float(arg("--width", "1"))
CLEAN = float(arg("--clean", "0"))   # 小さな影/日なたの点を消す(px)
BLUR = float(arg("--blur", "2"))
SUN = [float(c) for c in arg("--sun", "50,0,35").split(",")]   # 度: X, Y, Z

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch          # noqa: E402
from mathutils import Vector  # noqa: E402

fp_batch.install_addon()
import importlib              # noqa: E402
compat = importlib.import_module(fp_batch.ADDON_NAME + ".compat")
line_weight = importlib.import_module(fp_batch.ADDON_NAME + ".line_weight")

OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
meshes, others = fp_batch.append_objects(Path(MODEL))
fp_batch.normalize(meshes + others, meshes)

# 正面やや斜めの立ち姿。カメラは全身が入るよう合わせる
bpy.context.view_layer.update()
keep = fp_batch.dominant_cluster(meshes)
for o in meshes:
    if o.name not in keep and o not in keep:
        o.hide_render = True
vis = [o for o in meshes if not o.hide_render]
pts = [o.matrix_world @ Vector(c) for o in vis for c in o.bound_box]
print("@@@ meshes", len(meshes), "visible", len(vis), flush=True)
zmin = min(p.z for p in pts); zmax = max(p.z for p in pts)
cd = bpy.data.cameras.new("Cam"); cd.lens = 70
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam); sc.camera = cam
cam.rotation_euler = (math.radians(86), 0, math.radians(20))
sc.render.resolution_x, sc.render.resolution_y = int(RES * 0.75), RES
bpy.context.view_layer.update()
loc, _ = cam.camera_fit_coords(bpy.context.evaluated_depsgraph_get(),
                               [v for p in pts for v in p])
ctr = sum(pts, Vector()) / len(pts)
cam.location = ctr + (loc - ctr) * 1.08

sun_d = bpy.data.lights.new("Sun", "SUN"); sun_d.energy = 4.0
sun_d.angle = math.radians(0.5)
sun = bpy.data.objects.new("Sun", sun_d); sc.collection.objects.link(sun)
sun.rotation_euler = tuple(math.radians(a) for a in SUN)
sc.eevee.taa_render_samples = 32


def shot(name):
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", name, flush=True)


for p_ in ("fp_use_random_seed", "fp_auto_detect_aov"):
    setattr(sc, p_, False)
sc.fp_auto_style = STYLE
for o in vis:
    o.select_set(True)
bpy.context.view_layer.objects.active = vis[0]
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
shot("a_step0")
print("@@@ dd pass", bpy.context.view_layer.use_pass_diffuse_direct, [ (o.name, o.hide_render) for o in sc.objects if o.type == "LIGHT"], sc.render.engine, flush=True)
if "--mono" in ARGV:
    sc.fp_preview_mode = "MONO_LIGHT"
    shot("a2_mono")
    sc.fp_preview_mode = "WHITE"
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "a_step0.blend"))

# ---- 試作のノード -------------------------------------------------------
vl = bpy.context.view_layer
# 材質の光ではなく、白い拡散面として受けた光(影込み)を AOV に出す。
# アニメ調のモデルは発光や Shader to RGB の材質が多く、直接光のパスが 0 になる
SHADE = "fp_shade"
if SHADE not in [a.name for a in vl.aovs]:
    a = vl.aovs.add(); a.name = SHADE; a.type = "VALUE"
done = set()
for o in vis:
    for slot in o.material_slots:
        m = slot.material
        if m is None or m.name in done or not m.use_nodes:
            continue
        done.add(m.name)
        nt = m.node_tree
        dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
        dif.inputs["Color"].default_value = (1, 1, 1, 1)
        s2r = nt.nodes.new("ShaderNodeShaderToRGB")
        aov = nt.nodes.new("ShaderNodeOutputAOV")
        aov.aov_name = SHADE
        nt.links.new(dif.outputs[0], s2r.inputs[0])
        nt.links.new(s2r.outputs["Color"], aov.inputs["Value"])
print("@@@ shade materials", len(done), flush=True)
tree = compat.get_compositor_tree(sc)
rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
comp = next(n for n in tree.nodes if n.type in compat.OUTPUT_NODE_TYPES)
# Composite へ入る線(縮小の前があればそこ)。影線は等倍で足してから縮小させる
target = comp.inputs[0]
src = target.links[0].from_socket
if src.node.type == "SCALE":
    target = src.node.inputs[0]
    src = target.links[0].from_socket
dd = compat.render_layer_socket(rl, (SHADE,))
alpha = compat.render_layer_socket(rl, ("Alpha",))
ss = 2.0 if sc.render.resolution_percentage == 200 else 1.0


def node(t, x, y):
    n = tree.nodes.new(t); n.location = (x, y); n.label = "FP_ShadowProto"; return n


bw = node("CompositorNodeRGBToBW", 300, -900)
tree.links.new(dd, bw.inputs[0])
# 直接光の強さは日の強さで変わる。しきい値は「日なたの明るさ」に対する割合で切る
# (日なたは energy * cos で 0..energy。試作なので energy で割るだけ)
div = node("CompositorNodeMath", 480, -900); div.operation = "DIVIDE"
tree.links.new(bw.outputs[0], div.inputs[0]); div.inputs[1].default_value = sun_d.energy / math.pi
blur = node("CompositorNodeBlur", 640, -900)
compat.set_node_value(blur, "filter_type", "GAUSS")
for k, v in (("size_x", int(BLUR * ss)), ("size_y", int(BLUR * ss))):
    try:
        setattr(blur, k, v)
    except Exception:
        pass
if "Size" in blur.inputs:
    blur.inputs["Size"].default_value = (BLUR * ss, BLUR * ss) if hasattr(blur.inputs["Size"].default_value, "__len__") else BLUR * ss
tree.links.new(div.outputs[0], blur.inputs[0])
gt = node("CompositorNodeMath", 800, -900); gt.operation = "GREATER_THAN"
tree.links.new(blur.outputs[0], gt.inputs[0]); gt.inputs[1].default_value = THR
# 物の外は影にしない(アルファで切る)
lit = node("CompositorNodeMath", 960, -900); lit.operation = "MAXIMUM"
inv_a = node("CompositorNodeMath", 960, -1050); inv_a.operation = "SUBTRACT"
inv_a.inputs[0].default_value = 1.0
tree.links.new(line_weight.silhouette(tree, rl, sc, 960, -1200, label="FP_ShadowProto"), inv_a.inputs[1])
lit_src = gt.outputs[0]
if CLEAN > 0:
    # 開いて閉じる: 小さい日なたの点を消し(縮めて戻す)、小さい影の点を消す(広げて戻す)
    def de(sock, d, x):
        n = node("CompositorNodeDilateErode", x, -1000)
        compat.set_node_value(n, "mode", "STEP")
        try:
            n.distance = int(round(d))
        except Exception:
            n.inputs["Size"].default_value = int(round(d))
        tree.links.new(sock, n.inputs[0]); return n.outputs[0]
    k = CLEAN * ss
    lit_src = de(de(de(de(lit_src, -k, 820), k, 840), k, 860), -k, 880)
tree.links.new(lit_src, lit.inputs[0]); tree.links.new(inv_a.outputs[0], lit.inputs[1])
# 境界: 膨らませた影 - 影 (線幅 WIDTH*ss px)
dil = node("CompositorNodeDilateErode", 1120, -900)
compat.set_node_value(dil, "mode", "STEP")
try:
    dil.distance = int(round(WIDTH * ss))
except Exception:
    dil.inputs["Size"].default_value = int(round(WIDTH * ss))
tree.links.new(lit.outputs[0], dil.inputs[0])
edge = node("CompositorNodeMath", 1280, -900); edge.operation = "SUBTRACT"
edge.use_clamp = True
tree.links.new(dil.outputs[0], edge.inputs[0]); tree.links.new(lit.outputs[0], edge.inputs[1])

# 影のベタ: 影の所を少し灰色に掛ける
fill = node("CompositorNodeMixRGB", 1440, -700); fill.blend_type = "MULTIPLY"
fill.inputs[2].default_value = (0.78, 0.80, 0.86, 1)
inv_lit = node("CompositorNodeMath", 1280, -700); inv_lit.operation = "SUBTRACT"
inv_lit.inputs[0].default_value = 1.0; tree.links.new(lit.outputs[0], inv_lit.inputs[1])
tree.links.new(inv_lit.outputs[0], fill.inputs[0])
tree.links.new(src, fill.inputs[1])

mix = node("CompositorNodeMixRGB", 1600, -600); mix.blend_type = "MIX"
mix.inputs[2].default_value = (*COLOR, 1)
tree.links.new(edge.outputs[0], mix.inputs[0])

# 線画(黒)を上に戻す: 色の線は黒線の下に。min(元の線, 色を足した絵)
dark = node("CompositorNodeMixRGB", 1760, -600); dark.blend_type = "DARKEN"
dark.inputs[0].default_value = 1.0
tree.links.new(mix.outputs[0], dark.inputs[1]); tree.links.new(src, dark.inputs[2])

# 途中の絵(確かめ用)
tree.links.new(div.outputs[0], target)
shot("b0_light")
tree.links.new(blur.outputs[0], target)
shot("b1_blur")
# b: マスク
tree.links.new(lit.outputs[0], target)
shot("b_mask")
# c: 色の線だけ
tree.links.new(src, mix.inputs[1])
tree.links.new(dark.outputs[0], target)
shot("c_shadowline")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "c_shadowline.blend"))
# d: 色の線 + 影のベタ
tree.links.new(fill.outputs[0], mix.inputs[1])
shot("d_line_fill")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "d_line_fill.blend"))
