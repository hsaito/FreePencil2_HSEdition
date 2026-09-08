"""手で触るための .blend を作る。GUI で開いてすぐ試せる状態にする。

スザンヌ(サブサーフ2適用)・カメラ・1灯を置き、STEP0 まで通しておく。
開いたら N キーのサイドバーで FreePencil のパネルが出るので、
STEP3 の「線の強弱(くぼみ)」を触るだけで比べられる。

設定は出荷時の既定のまま(細線化ON)にしてある。F12 のキャンバスが
2倍になる件も、そのまま再現できる。

  blender -b --factory-startup --python make_tryout_blend.py -- \
      --out <dir>
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "tryout"))).resolve()
RES_W = int(arg("--res", "1920"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W), "--ss", "1"]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16


def main() -> None:
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    o.name = "Suzanne"
    m = o.modifiers.new("Subdivision", "SUBSURF")
    m.levels = m.render_levels = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    meshes = [o]
    dm.grey(meshes)

    sc = bpy.context.scene
    pts = [ob.matrix_world @ Vector(c) for ob in meshes for c in ob.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    center = Vector(((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5,
                     (min(zs) + max(zs)) * 0.5))
    r = max((p - center).length for p in pts)
    cd = bpy.data.cameras.new("Camera")
    cd.lens = 55.0
    cam = bpy.data.objects.new("Camera", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(20.0)

    def place(d):
        cam.location = (center.x + math.sin(a) * d, center.y - math.cos(a) * d,
                        center.z + d * 0.14)
        cam.rotation_euler = (center - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    from bpy_extras.object_utils import world_to_camera_view
    dist = r * 3.0
    for _ in range(3):
        place(dist)
        mx = max(max(abs(world_to_camera_view(sc, cam, p).x - 0.5) * 2.0,
                     abs(world_to_camera_view(sc, cam, p).y - 0.5) * 2.0)
                 for p in pts)
        dist *= mx * 1.10
    place(dist)
    cd.clip_end = dist * 30

    w = bpy.data.worlds.new("World")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1.0)
        bg.inputs[1].default_value = 0.15
    sc.world = w
    lt = bpy.data.lights.new("Key", type="SUN")
    lt.energy = 3.0
    lt.angle = 0.0
    key = bpy.data.objects.new("Key", lt)
    sc.collection.objects.link(key)
    key.rotation_euler = (math.radians(62), 0.0, math.radians(40) + a)

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    # 出荷時の既定で通す。ここを触ると「実物と違うもの」を渡すことになる
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    bpy.ops.object.select_all(action="DESELECT")
    for ob in meshes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    # くぼみの半径だけはモデルの大きさに合わせておく。
    # 既定 0.6 は「半径1くらいのモデル」を想定した値なので、
    # 大きいモデルだと何も遮蔽されず強弱が付かない
    sc.fp_lw_ao_dist = r * 0.6

    dst = OUT / "tryout.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(dst))
    print(f"@@@ 保存 {dst}")
    print(f"@@@ 解像度 {sc.render.resolution_x}x{sc.render.resolution_y} "
          f"{sc.render.resolution_percentage}%  細線化 {sc.fp_supersample}")
    print(f"@@@ くぼみの半径 {sc.fp_lw_ao_dist:.3f}  強弱 {sc.fp_line_weight}")


if __name__ == "__main__":
    main()
