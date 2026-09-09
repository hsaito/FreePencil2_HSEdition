"""eggs_bowl の後退が「多パーツ判定の取りこぼし」で説明できるかを確かめる。

eggs_bowl は卵1個が1オブジェクトで、75個が選択されている。本体の
コメントどおりなら「オブジェクトが8個以上 -> 多パーツ」で 60度 に
落ちるはずで、人工分割の下限は関係ないはずだった。

ところが vertex_color.py は同じメッシュを共有するリンク複製を1つに
まとめてから数えている(75 -> 4)。そのため many_loose_parts が False
になり、人工分割の枝へ落ちて 9.43度 で切られていた。

ここでは本体を触らず、判定に渡る many_parts だけを差し替えて、
数が正しければ絵がどうなるかを見る。

  blender -b --factory-startup --python eval_eggs_parts.py -- [--res 900]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "eggs_parts"))).resolve()
RES = int(arg("--res", "900"))

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
FORCE_PARTS = [False]


def say(m):
    print(f"@@@ {m}", flush=True)


def patch():
    from freepencil2 import utils
    real = utils.choose_auto_threshold

    def probe(angles, has_armature=False, many_parts=False,
              has_subsurf=False, split_floor=None):
        if FORCE_PARTS[0]:
            many_parts = True
        deg, merge = real(angles, has_armature, many_parts,
                          has_subsurf, split_floor)
        return deg, merge

    utils.choose_auto_threshold = probe


def stage(meshes):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    ctr = Vector((sum(p.x for p in pts) / len(pts),
                  sum(p.y for p in pts) / len(pts),
                  sum(p.z for p in pts) / len(pts)))
    r = max((p - ctr).length for p in pts)
    cd = bpy.data.cameras.new("C")
    cd.lens = 55.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(30.0)
    d = r * 3.1
    cam.location = (ctr.x + math.sin(a) * d, ctr.y - math.cos(a) * d,
                    ctr.z + d * 0.22)
    cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat(
        "-Z", "Y").to_euler()
    cd.clip_end = d * 30
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(62), 0.0, math.radians(40) + a)


def run(path, floor, ridge, force, tag):
    FORCE_PARTS[0] = force
    meshes, _ = dm.load(path)
    dm.grey(meshes)
    stage(meshes)
    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_split_floor = floor
    sc.fp_auto_merge = False
    sc.fp_min_island_area_pct = 1.0
    sc.fp_ridge_amount = ridge
    sc.fp_ridge_radius = 0.08
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES * 2
    sc.render.resolution_y = RES * 2
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    fp_batch.render_still(sc, OUT / f"{tag}.png", 2)
    say(f"{tag} 完了")


def main():
    fp_batch.install_addon()
    patch()
    path = next(m["path"] for m in scan_models.scan(scan_models.DEFAULT_ROOT)
                if "eggs_bowl" in Path(m["path"]).stem)
    run(path, 5.0, 0.25, False, "a_now")            # いま
    run(path, 14.0, 0.45, False, "b_new")           # 提案。卵が潰れた
    run(path, 14.0, 0.45, True, "c_parts_fixed")    # 多パーツを正しく数えたら
    run(path, 5.0, 0.25, True, "d_parts_now")       # いまの設定 + 正しい数え方


if __name__ == "__main__":
    main()
