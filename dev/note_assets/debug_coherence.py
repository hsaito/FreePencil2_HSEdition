"""縞の向きのそろい具合(構造テンソル)と詰まり具合をそのまま画像に出す。
  blender -b --factory-startup --python debug_coherence.py -- --blend X.blend --frame 250 --out out/stripe_verify/coh_town [--aov mecha_color]
町(shoot_town_v2.aim)か試験場(test_grazing.cam_at --height)でカメラを置く。
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(Path(arg("--blend")).resolve()))
sc = bpy.context.scene
res = int(arg("--res", "1280"))
sc.render.resolution_x, sc.render.resolution_y = res, res * 9 // 16
sc.render.resolution_percentage = int(arg("--pct", str(sc.render.resolution_percentage)))
print("@@@ pct", sc.render.resolution_percentage, flush=True)
sc.eevee.taa_render_samples = 4
if "--keep-cam" in ARGV:
    res = int(arg("--res", "800"))
    sc.render.resolution_x = sc.render.resolution_y = res
elif arg("--height"):
    import test_grazing as tg
    pos, tgt = tg.cam_at(float(arg("--height")))
    sc.camera.location = pos
    sc.camera.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
else:
    import shoot_town_v2 as st
    f = int(arg("--frame", "250"))
    st.FRAMES = 720
    st.aim(sc.camera, f)
    sc.frame_set(f + 1)
import importlib
lw = importlib.import_module(next(m for m in sys.modules if m.endswith(".line_weight")))
t = sc.node_tree
rl = next(n for n in t.nodes if n.type == "R_LAYERS")
comp = next(n for n in t.nodes if n.type == "COMPOSITE")
out = Path(arg("--out")).resolve()
out.mkdir(parents=True, exist_ok=True)
for aov in arg("--aov", "mecha_color,fine_color").split(","):
    if aov not in rl.outputs:
        print("@@@ no", aov)
        continue
    made = []
    rp = max(1, int(round(lw.STRIPE_R * sc.render.resolution_percentage / 200.0)))
    coh = lw._coherence(t, rl.outputs[aov], rp, 2000, -3000, made)
    for lk in list(comp.inputs[0].links):
        t.links.remove(lk)
    t.links.new(coh.outputs[0], comp.inputs[0])
    sc.render.filepath = str(out / f"coh_{aov}.png")
    comp_ok = sc.render.use_compositing
    sc.render.film_transparent = False
    bpy.ops.render.render(write_still=True)
    for n in made:
        t.nodes.remove(n)
    # 素の色も
    for lk in list(comp.inputs[0].links):
        t.links.remove(lk)
    t.links.new(rl.outputs[aov], comp.inputs[0])
    sc.render.filepath = str(out / f"col_{aov}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", aov, flush=True)
