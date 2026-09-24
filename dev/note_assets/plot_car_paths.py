"""走る車の位置を真上から 1 秒ごとに描く(重なり・突き当たりへの突っ込みを見る)。描画はしない。"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.argv = ["blender", "--", "--blend", str(HERE / "out/stripe_verify/town_stripe.blend")]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch, json
import shoot_town_v2 as st
fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(st.BLEND))
sc = bpy.context.scene
st.moving_cars(sc)
cars = [o for o in sc.objects if o.type == "MESH" and o.name.startswith("asset_")
        and any(k in o.name for k in ("police", "toyota", "lancia", "hyundai", "audi", "mclaren"))
        and not o.hide_render]
out = {"t": [], "cars": {o.name: [] for o in cars}}
for f in range(0, st.FRAMES, 6):
    sc.frame_set(f + 1)
    out["t"].append(f / st.FPS)
    for o in cars:
        m = o.matrix_world.translation
        out["cars"][o.name].append((m.x, m.y, o.dimensions.x, o.dimensions.y, o.matrix_world.to_euler().z))
(HERE / "out/town_v4/car_paths.json").write_text(json.dumps(out))
print("@@ cars", len(cars))
