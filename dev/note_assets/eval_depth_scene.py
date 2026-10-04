"""前後に重なった別々のものに、境目の線が出るかを確かめる。

深度チャンネルは単体アセット10体では 0.5 から 2.0 まで振っても
絵が1画素も変わらなかった。ただしどれも「1個を画面中央に置いた絵」で、
別々のものが前後に重なる場面が無かった。実際のイラストで深度が要る
のはそこなので、その場面を自分で作って見る。

作るもの: 同じ種類のアセットを奥行き方向に3つ並べ、画面上で重ねる。
色は塗り分けが別々に振るが、同じメッシュを使うので同じ色になりやすい。
重なった縁に線が出なければ、手前と奥が溶けて1つの塊に見える。

  blender -b --factory-startup --python eval_depth_scene.py -- [--res 900]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "depth_scene"))).resolve()
RES = int(arg("--res", "900"))
PICK = arg("--model", "clay-vase")

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)


def say(m):
    print(f"@@@ {m}", flush=True)


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    ctr = Vector(((min(xs) + max(xs)) * .5, (min(ys) + max(ys)) * .5,
                  (min(zs) + max(zs)) * .5))
    return ctr, max((p - ctr).length for p in pts)


def build(path):
    """1体を読み込み、奥行き方向に3つ並べて画面で重ねる。"""
    meshes, _ = dm.load(path)
    dm.grey(meshes)
    ctr, r = bounds(meshes)
    sc = bpy.context.scene
    made = list(meshes)
    # 手前・中・奥。横に少しずらして輪郭を重ねる
    for k, (dy, dx) in enumerate(((-1.15, 0.75), (1.15, -0.75)), start=1):
        copies = []
        for o in meshes:
            c = o.copy()
            c.data = o.data          # リンク複製。色が同じになりやすい条件
            sc.collection.objects.link(c)
            c.location = (o.location.x + r * dx, o.location.y + r * dy,
                          o.location.z)
            copies.append(c)
        made += copies
        say(f"複製 {k}: {len(copies)}個  ずらし y{r * dy:+.2f} x{r * dx:+.2f}")
    return made


def stage(objs):
    sc = bpy.context.scene
    ctr, r = bounds(objs)
    cd = bpy.data.cameras.new("C")
    cd.lens = 85.0                    # 望遠寄り。前後の重なりを強くする
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    from bpy_extras.object_utils import world_to_camera_view

    def place(d):
        cam.location = (ctr.x, ctr.y - d, ctr.z + d * 0.10)
        cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    # 3つ全部が枠に入るまで引く。1つだけ大写しになると重なりが見えない
    d = r * 3.0
    for _ in range(4):
        place(d)
        m = max(max(abs(world_to_camera_view(sc, cam, p).x - .5) * 2,
                    abs(world_to_camera_view(sc, cam, p).y - .5) * 2)
                for p in pts)
        d *= m * 1.08
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


def run(path, depth, tag):
    objs = build(path)
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
    path = next(m["path"] for m in scan_models.scan(scan_models.DEFAULT_ROOT)
                if PICK in Path(m["path"]).stem)
    say(f"使うモデル {Path(path).stem}")
    for dv, tag in ((0.0, "a_depth0"), (1.0, "b_depth1"),
                    (1.5, "c_depth15"), (2.0, "d_depth2")):
        run(path, dv, tag)


if __name__ == "__main__":
    main()
