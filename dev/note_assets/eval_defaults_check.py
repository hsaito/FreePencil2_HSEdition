"""既定値を変えた効果を、出荷どおりの経路で確かめる。

これまでの評価スクリプトは fp_auto_merge を切って角度と稜線を手で
入れていた。既定値を変えたのだから、今度は何も上書きせず STEP0 に
任せた状態で撮らないと「既定が本当に効いているか」の確認にならない。

    old  fp_auto_split_floor=5.0 / 稜線0.25 を手で入れる(変更前の挙動)
    new  何も上書きしない(出荷時の既定)

あわせて、new のときに実際に選ばれた角度と稜線の値を印字する。
絵が変わっていても、それが既定の変更のせいだと言えなければ意味がない。

  blender -b --factory-startup --python eval_defaults_check.py -- [--res 900]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "defaults"))).resolve()
RES = int(arg("--res", "900"))
WANT = arg("--only", "eggs_bowl,formal-shoe,basketball_2K,cleaver_knife,"
                     "cupcakes,baccarat,arched_hangar,kaino-school,"
                     "anime-girl,lancia")

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
CHOSEN = []

# スザンヌの見るところ。(方位, 仰角, 注視点, 距離)
SUZ_VIEWS = {"ear": (208.0, 12.0, Vector((1.25, 0, 0.35)), 2.4),
             "face": (20.0, 8.0, Vector((0, 0, 0.1)), 5.2)}


def say(m):
    print(f"@@@ {m}", flush=True)


def watch():
    """実際に選ばれた角度を記録する。既定が効いたかの証拠になる。"""
    from freepencil2 import utils
    real = utils.choose_auto_threshold

    def probe(angles, has_armature=False, many_parts=False,
              has_subsurf=False, split_floor=None):
        deg, merge = real(angles, has_armature, many_parts,
                          has_subsurf, split_floor)
        CHOSEN.append((round(float(deg), 2), split_floor))
        return deg, merge

    utils.choose_auto_threshold = probe


def common(sc):
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


def as_old(sc):
    """変更前の挙動を手で作る。STEP0 のおすすめ設定を切って入れ直す。"""
    sc.fp_auto_split_floor = 5.0
    sc.fp_auto_merge = False
    sc.fp_min_island_area_pct = 1.0
    sc.fp_ridge_amount = 0.25
    sc.fp_ridge_radius = 0.08


def light(sc, az_off=0.0):
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
    lo.rotation_euler = (math.radians(62), 0, math.radians(40) + az_off)


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


def paint_and_render(objs, png):
    sc = bpy.context.scene
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    fp_batch.render_still(sc, png, 2)
    return sc.fp_ridge_amount, sc.fp_auto_split_floor


def run_model(path, old, tag):
    meshes, _ = dm.load(path)
    dm.grey(meshes)
    stage(meshes)
    sc = bpy.context.scene
    common(sc)
    if old:
        as_old(sc)
    CHOSEN.clear()
    ridge, floor = paint_and_render(meshes, OUT / f"{tag}.png")
    return ridge, floor, list(CHOSEN)


def run_suzanne(old, tag):
    out = {}
    for vn, (az, el, tgt, d) in SUZ_VIEWS.items():
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
        if old:
            as_old(sc)
        cd = bpy.data.cameras.new("C")
        cd.lens = 70.0
        cd.clip_end = 100
        cam = bpy.data.objects.new("C", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
        a, e = math.radians(az), math.radians(el)
        cam.location = (tgt.x + math.sin(a) * math.cos(e) * d,
                        tgt.y - math.cos(a) * math.cos(e) * d,
                        tgt.z + math.sin(e) * d)
        cam.rotation_euler = (tgt - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        light(sc)
        CHOSEN.clear()
        out[vn] = paint_and_render([o], OUT / f"suzanne_{vn}_{tag}.png") \
            + (list(CHOSEN),)
    return out


def main():
    fp_batch.install_addon()
    watch()
    for old, tag in ((True, "old"), (False, "new")):
        r = run_suzanne(old, tag)
        for vn, (ridge, floor, chosen) in r.items():
            say(f"スザンヌ {vn:<5} {tag:<3} 稜線{ridge:.2f} 下限{floor:.1f} "
                f"選ばれた角度 {chosen}")
    pats = [x for x in WANT.split(",") if x]
    models = [m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
              if any(p in Path(m["path"]).stem for p in pats)]
    for m in models:
        name = Path(m["path"]).stem[:28]
        for old, tag in ((True, "old"), (False, "new")):
            try:
                ridge, floor, chosen = run_model(m["path"], old,
                                                 f"{name}_{tag}")
            except Exception as e:                  # noqa: BLE001
                say(f"{name} {tag}: 失敗 {type(e).__name__}")
                continue
            say(f"{name:<30} {tag:<3} 稜線{ridge:.2f} 下限{floor:.1f} "
                f"角度{sorted({c[0] for c in chosen})}")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
