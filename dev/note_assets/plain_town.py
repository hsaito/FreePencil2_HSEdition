"""町の「3D だけ」(線を出さない)絵を撮る。60 秒デモの冒頭のワイプ用。
  blender -b --factory-startup --python plain_town.py -- --frames 1-120 [--preview] [--out out/demo60/town_plain]
"""
import sys
from pathlib import Path
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
prev = "--preview" in ARGV
a, b = map(int, arg("--frames", "1-120").split("-"))
OUT = Path(arg("--out", str(HERE / "out" / "demo60" / ("town_plain_preview" if prev else "town_plain")))).resolve()
sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch
import shoot_town_v2 as st
fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(HERE / "out" / "stripe_verify" / "town_stripe.blend"))
sc = bpy.context.scene
st.FRAMES = 720
st.moving_cars(sc)
res = 960 if prev else 1920
sc.render.resolution_x, sc.render.resolution_y = res, res * 9 // 16
sc.eevee.taa_render_samples = 4 if prev else 32
sc.render.use_compositing = False          # 線を出さない = 陰影だけの 3D
sc.render.film_transparent = True       # 空は透明(線画と同じ白地に重ねる)
# 日陰の面が真っ黒になった(光が太陽だけ)。周りから明るさを足す
w = sc.world or bpy.data.worlds.new("W")
sc.world = w
w.use_nodes = True
bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.8, 0.8, 0.82, 1.0)
bg.inputs["Strength"].default_value = float(arg("--ambient", "0.9"))
if "--vcol" in ARGV:                       # 塗り分け(mecha_color)を素通しで
    m = bpy.data.materials.new("look_mecha")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_type = "GEOMETRY"
    at.attribute_name = "mecha_color"
    em = nt.nodes.new("ShaderNodeEmission")
    mo = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], mo.inputs["Surface"])
    for ob in sc.objects:
        if ob.type != "MESH":
            continue
        for ms in ob.material_slots:
            ms.link = "OBJECT"
            ms.material = m
        if not ob.material_slots:
            ob.data.materials.append(m)
    sc.view_settings.view_transform = "Standard"
OUT.mkdir(parents=True, exist_ok=True)
for f in range(a, b + 1):
    st.aim(sc.camera, f - 1)
    sc.frame_set(f)
    sc.render.filepath = str(OUT / f"f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
print("@@@ done", flush=True)
