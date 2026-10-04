"""横切る車(カット A で手前を走るコピー)がカメラに写るフレームを数える(描画はしない)。"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.argv = ["blender", "--", "--blend", str(HERE / "out/stripe_verify/town_stripe.blend")]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
import shoot_town_v2 as st
fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(st.BLEND))
sc = bpy.context.scene
before = set(sc.objects)
st.moving_cars(sc)
new = [o for o in sc.objects if o not in before and o.type == "MESH" and not o.name.startswith("wheel_")]
car = new[0]
vis = []
for f in range(st.FRAMES):
    st.aim(sc.camera, f)
    sc.frame_set(f + 1)
    dg = bpy.context.evaluated_depsgraph_get()
    mw = car.evaluated_get(dg).matrix_world
    pts = [world_to_camera_view(sc, sc.camera, mw @ Vector(c)) for c in car.bound_box]
    if any(0 <= p.x <= 1 and 0 <= p.y <= 1 and p.z > 0 for p in pts):
        vis.append(f)
print("@@", car.name, len(vis), vis[:3], vis[-3:], flush=True)
print("@@LIST", ",".join(map(str, vis)), flush=True)
