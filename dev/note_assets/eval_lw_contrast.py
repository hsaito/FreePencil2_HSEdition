"""強弱をもっと強くする案を並べて見る。

いまの段は 6/5/4/3/2 px(2倍レンダ、縮小後 3〜1px)で最太÷最細は 3倍。
fp_lw_strength は全段に同じ倍率を掛けるので、太くはなるが比は 3倍の
まま。「もっと強く」は比を広げることなので、段の並びを変えて比べる。

調べている途中で2つ分かった。
  - 段分けが働いていなかった。計測は生の AO、合成はぼかした AO で、
    線の画素の 88% が一番細い段に入っていた(eval_lw_bands.py)
  - 段の向きが逆だった。k=0(一番浅い)に一番太い段が当たっていた
どちらも line_weight.py 側で直してある。ここはその後の比較。

太さは整数画素で頭打ち(6/5/4/3/2 は縮小後 3/2/2/2/1 に潰れる)なので、
濃さの強弱(fp_lw_tone)も並べる。最細は 2px(縮小後1px)から下げない。
1px だと縮小で破線になった(実測)。

  blender -b --factory-startup --python eval_lw_contrast.py -- [--res 1400]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "lw_contrast"))).resolve()
RES = int(arg("--res", "1400"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)

# (名前, 段, 強さ倍率, 濃さの強弱)
VARIANTS = [("now", (6, 5, 4, 3, 2), 1.0, 0.0),
            ("tone05", (6, 5, 4, 3, 2), 1.0, 0.5),
            ("tone10", (6, 5, 4, 3, 2), 1.0, 1.0),
            ("w4x", (8, 6, 4, 3, 2), 1.0, 0.0),
            ("w4x_tone05", (8, 6, 4, 3, 2), 1.0, 0.5),
            ("w6x_tone05", (12, 8, 5, 3, 2), 1.0, 0.5)]
VIEWS = {"front": (20.0, 8.0), "quarter": (52.0, 10.0)}


def say(m):
    print(f"@@@ {m}", flush=True)


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("S", "SUBSURF")
    m.levels = m.render_levels = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    dm.grey([o])
    return o


def stage():
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("C")
    cd.lens = 70.0
    cd.clip_end = 100
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(62), 0, math.radians(40))
    return cam


def aim(cam, az, el, tgt=Vector((0, 0, 0.1)), d=5.2):
    a, e = math.radians(az), math.radians(el)
    cam.location = (tgt.x + math.sin(a) * math.cos(e) * d,
                    tgt.y - math.cos(a) * math.cos(e) * d,
                    tgt.z + math.sin(e) * d)
    cam.rotation_euler = (tgt - Vector(cam.location)).to_track_quat(
        "-Z", "Y").to_euler()
    bpy.context.view_layer.update()


def main():
    fp_batch.install_addon()
    from freepencil2 import line_weight
    o = build()
    cam = stage()
    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_line_weight = True
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES * 2
    sc.render.resolution_y = RES * 2
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    aim(cam, *VIEWS["front"])
    bpy.ops.freepencil.measure_line_weight()
    edges = [round(getattr(sc, f"fp_lw_e{i}"), 5) for i in range(1, 5)]
    say(f"しきい値 {edges}")

    orig = line_weight.LEVELS
    for tag, levels, strength, tone in VARIANTS:
        line_weight.LEVELS = tuple(levels)
        sc.fp_lw_strength = strength
        sc.fp_lw_tone = tone
        bpy.ops.freepencil2.link_button()        # STEP3 を組み直す
        sc.fp_white_preview = True
        px = line_weight.levels_from_scene(sc)
        for vn, (az, el) in VIEWS.items():
            aim(cam, az, el)
            fp_batch.render_still(sc, OUT / f"{vn}_{tag}.png", 2)
        say(f"{tag:<11} 段 {px}  最太÷最細 {px[0] / px[-1]:.1f}倍  濃さ {tone}")
    line_weight.LEVELS = orig
    (OUT / "variants.json").write_text(json.dumps(
        [{"tag": t, "levels": l, "strength": s, "tone": n}
         for t, l, s, n in VARIANTS],
        ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
