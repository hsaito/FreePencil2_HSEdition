"""段分けを直したあとで、詰まった線の守りがまだ効いているかを見る。

段分けが働いていなかった頃(88% が最細の段)は、深い所が実際には
太らなかった。直した今は、耳の縁のように平行線が何本も走る所が
全部「深い」段に入って、まとめて太る条件がそろう。詰まりの守り
(fp_lw_crowd)がそこを止められるかを、以前壊れた場所で確かめる。

    スザンヌの耳の裏 / カメラのレンズ / 車のグリル

候補の段と濃さを、いまの既定と並べる。

  blender -b --factory-startup --python eval_lw_crowd_check.py -- [--res 1200]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "lw_crowd"))).resolve()
RES = int(arg("--res", "1200"))

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

# (名前, 段, 濃さ)
# (名前, 段, 濃さ, くぼみのぼかし)
# (名前, 段, 濃さ, ぼかし, くぼみを太く)
CANDS = [("outline", (12, 8, 5, 3, 2), 0.25, 12, False),
         ("cavity", (12, 8, 5, 3, 2), 0.25, 12, True)]
MODELS = ["camera_2K", "lancia"]


def say(m):
    print(f"@@@ {m}", flush=True)


def common(sc):
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    # 出荷どおり: 細線化 ON (pct=200)。アドオンが太さを pct/200 で割る
    sc.fp_auto_supersample = True
    sc.fp_color_seed = 42
    sc.fp_white_preview = True
    sc.fp_line_weight = True
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True


def light(sc, az_off=0.0):
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(62), 0, math.radians(40) + az_off)


def setup_and_measure(objs):
    sc = bpy.context.scene
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    bpy.ops.freepencil.measure_line_weight()


def shoot_variants(prefix):
    from freepencil2 import line_weight
    sc = bpy.context.scene
    orig = line_weight.LEVELS
    for tag, levels, tone, blur, deep in CANDS:
        line_weight.LEVELS = tuple(levels)
        sc.fp_lw_tone = tone
        sc.fp_lw_ao_blur = blur
        sc.fp_lw_deep_thick = deep
        bpy.ops.freepencil.measure_line_weight()
        bpy.ops.freepencil2.link_button()
        sc.fp_white_preview = True
        assert sc.render.resolution_percentage == 200
        fp_batch.render_still(sc, OUT / f"{prefix}_{tag}.png", 1)
    line_weight.LEVELS = orig
    say(f"{prefix} 完了")


def suzanne_ear():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("S", "SUBSURF")
    m.levels = m.render_levels = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    dm.grey([o])
    sc = bpy.context.scene
    common(sc)
    cd = bpy.data.cameras.new("C")
    cd.lens = 70.0
    cd.clip_end = 100
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tgt, d = Vector((1.25, 0, 0.35)), 2.4
    a, e = math.radians(208.0), math.radians(12.0)
    cam.location = (tgt.x + math.sin(a) * math.cos(e) * d,
                    tgt.y - math.cos(a) * math.cos(e) * d,
                    tgt.z + math.sin(e) * d)
    cam.rotation_euler = (tgt - Vector(cam.location)).to_track_quat(
        "-Z", "Y").to_euler()
    light(sc)
    setup_and_measure([o])
    shoot_variants("ear")


def stage(meshes):
    sc = bpy.context.scene
    pts = [o.matrix_world @ Vector(c) for o in meshes
           for c in o.bound_box if not o.hide_render]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    ctr = Vector(((min(xs) + max(xs)) * .5, (min(ys) + max(ys)) * .5,
                  (min(zs) + max(zs)) * .5))
    r = max((p - ctr).length for p in pts)
    cd = bpy.data.cameras.new("C")
    cd.lens = 55.0
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(30.0)
    from bpy_extras.object_utils import world_to_camera_view

    def place(d):
        cam.location = (ctr.x + math.sin(a) * d, ctr.y - math.cos(a) * d,
                        ctr.z + d * 0.26)
        cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    d = r * 3.0
    for _ in range(3):
        place(d)
        m = max(max(abs(world_to_camera_view(sc, cam, p).x - .5) * 2,
                    abs(world_to_camera_view(sc, cam, p).y - .5) * 2)
                for p in pts)
        d *= m * 1.10
    place(d)
    cd.clip_end = d * 30
    light(sc, a)


def main():
    fp_batch.install_addon()
    suzanne_ear()
    for pat in MODELS:
        path = next(m["path"] for m in scan_models.scan(scan_models.DEFAULT_ROOT)
                    if pat in Path(m["path"]).stem)
        meshes, _ = dm.load(path)
        dm.grey(meshes)
        stage(meshes)
        common(bpy.context.scene)
        setup_and_measure(meshes)
        shoot_variants(Path(path).stem[:12])
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
