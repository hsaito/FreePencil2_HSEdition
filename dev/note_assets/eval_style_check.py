"""STEP0 の仕上がり(精密 / 強弱)を、何も上書きせずボタンだけで撮る。

「精密(メカ)」は v2.7 の出力そのもの、「強弱(手描き)」は AO の強弱・
14度・稜線0.45・しきい値の計測まで STEP0 が全部入れる。使う人が
プルダウンを切り替えて STEP0 を押したときの絵を、そのまま並べる。

  blender -b --factory-startup --python eval_style_check.py -- [--res 1200]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "style"))).resolve()
RES = int(arg("--res", "1200"))
WANT = arg("--only", "camera_2K,lancia,anime-girl,eggs_bowl")

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
STYLES = (("precise", 'PRECISE'), ("weighted", 'WEIGHTED'))


def say(m):
    print(f"@@@ {m}", flush=True)


def common(sc):
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.fp_white_preview = True
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


def shoot(objs, prefix):
    sc = bpy.context.scene
    for tag, style in STYLES:
        sc.fp_auto_style = style
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sc.fp_white_preview = True
        assert sc.render.resolution_percentage == 200
        fp_batch.render_still(sc, OUT / f"{prefix}_{tag}.png", 1)
        say(f"{prefix} {tag}: 下限{sc.fp_auto_split_floor} 稜線{sc.fp_ridge_amount:.2f} "
            f"強弱{sc.fp_line_weight} しきい値{[round(getattr(sc, f'fp_lw_e{i}'), 3) for i in range(1, 5)]}")


def suzanne(view, prefix):
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
    az, el, tgt, d = view
    a, e = math.radians(az), math.radians(el)
    cam.location = (tgt.x + math.sin(a) * math.cos(e) * d,
                    tgt.y - math.cos(a) * math.cos(e) * d,
                    tgt.z + math.sin(e) * d)
    cam.rotation_euler = (tgt - Vector(cam.location)).to_track_quat(
        "-Z", "Y").to_euler()
    light(sc)
    shoot([o], prefix)


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
    suzanne((20.0, 8.0, Vector((0, 0, 0.1)), 5.2), "suzanne_face")
    suzanne((208.0, 12.0, Vector((1.25, 0, 0.35)), 2.4), "suzanne_ear")
    pats = [x for x in WANT.split(",") if x]
    for m in scan_models.scan(scan_models.DEFAULT_ROOT):
        stem = Path(m["path"]).stem
        if not any(p in stem for p in pats):
            continue
        meshes, _ = dm.load(m["path"])
        dm.grey(meshes)
        stage(meshes)
        common(bpy.context.scene)
        shoot(meshes, stem[:12])
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
