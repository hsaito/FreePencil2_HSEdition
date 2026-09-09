"""前後に重なった別々のものに境目の線が出るか。自分で組んだ場面で見る。

深度チャンネルは単体アセット10体では 0.5→2.0 で1画素も変わらなかった。
どれも「1個を中央に置いた絵」で、別々のものが前後に重なる場面が無い。
実際のイラストで深度が要るのはそこなので、その場面を作る。

スザンヌを3体、奥行き方向にずらして画面上で重ねる。3体は同じメッシュ
なので塗り分けが同じ色を割り当てやすく、「色では分けられないが距離は
違う」という深度チャンネル本来の出番になる。

見るところ: 手前の輪郭が奥の面を横切るところに線が引かれているか。
線が無ければ3体が溶けて1つの塊に見える。

  blender -b --factory-startup --python eval_depth_overlap.py -- [--res 900]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "depth_overlap"))).resolve()
RES = int(arg("--res", "900"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)

# (横, 奥行き) 単位はスザンヌの大きさ。手前ほど下に置く
PLACES = ((-0.75, -1.6), (0.0, 0.0), (0.75, 1.6))


def say(m):
    print(f"@@@ {m}", flush=True)


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    objs = []
    for i, (dx, dy) in enumerate(PLACES):
        bpy.ops.mesh.primitive_monkey_add(location=(dx, dy, -dy * 0.28))
        o = bpy.context.object
        o.name = f"M{i}"
        m = o.modifiers.new("S", "SUBSURF")
        m.levels = m.render_levels = 2
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.ops.object.shade_smooth()
        objs.append(o)
    dm.grey(objs)
    return objs


def stage(objs):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    ctr = Vector(((min(xs) + max(xs)) * .5, (min(ys) + max(ys)) * .5,
                  (min(zs) + max(zs)) * .5))
    cd = bpy.data.cameras.new("C")
    cd.lens = 90.0                 # 望遠。前後の重なりを強くする
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    from bpy_extras.object_utils import world_to_camera_view

    def place(d):
        cam.location = (ctr.x, ctr.y - d, ctr.z + d * 0.06)
        cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    d = 14.0
    for _ in range(4):
        place(d)
        m = max(max(abs(world_to_camera_view(sc, cam, p).x - .5) * 2,
                    abs(world_to_camera_view(sc, cam, p).y - .5) * 2)
                for p in pts)
        d *= m * 1.06
    place(d)
    cd.clip_end = d * 30
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (.5, .5, .52, 1)
        bg.inputs[1].default_value = .15
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = 0.0
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(58), 0, math.radians(28))


def run(depth, tag):
    objs = build()
    stage(objs)
    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES * 2
    sc.render.resolution_y = RES * 2
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_ch_depth = depth
    sc.fp_white_preview = True
    fp_batch.render_still(sc, OUT / f"{tag}.png", 2)
    say(f"{tag} (深度{depth}) 完了")


def main():
    fp_batch.install_addon()
    for dv, tag in ((0.0, "a_depth0"), (1.0, "b_depth1"),
                    (1.5, "c_depth15"), (2.0, "d_depth2")):
        run(dv, tag)


if __name__ == "__main__":
    main()
