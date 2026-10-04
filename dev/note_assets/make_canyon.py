"""超高層の峡谷(通りの両側に窓の格子が詰まった高層が並ぶ一点透視)。

デモの「背景の密度」と、「つぶれ / 軽減」の見本用。町の本体(車・木・人形)は使わず、
town_kit_more.tower の格子だけを、間隔と高さを変えて並べる。

  blender -b --factory-startup --python make_canyon.py -- \
      [--out out/canyon] [--res 960] [--samples 4] [--seed 3] [--only-build]

撮るもの(同じ形・同じカメラ):
  bg_relief1   手描き背景(既定。つぶれ軽減 ON)
  bg_relief0   手描き背景で「つぶれ軽減」「奥の線を控えめに」を 0 に
  precise      精密(v2.7 と同じ、線は均一)
STEP0 の後の絵は透過 PNG(白地の線画)。白地に重ねて見る。
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "canyon"))).resolve()
RES = int(arg("--res", "960"))
SAMPLES = int(arg("--samples", "4"))
SEED = int(arg("--seed", "3"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))

import bpy          # noqa: E402
import fp_batch     # noqa: E402
import town_kit_more as more   # noqa: E402

RW = 15.0            # 通りの半幅(30m の大通り)
Y0, Y1 = -70.0, 560.0    # 通りの手前の端と奥の端
PITCHES = tuple(float(v) for v in arg("--pitches", "0.6,0.75,0.9,1.2,1.5").split(","))
FHS = tuple(float(v) for v in arg("--fhs", "3.6").split(","))     # 階高(窓の段の細かさ)


def say(m):
    print(f"@@@ {m}", flush=True)


def layout(rng):
    """両側に、低層の基壇 + セットバックした高層の 2 段を、隙間ほぼなしで並べる。"""
    objs = []
    idx = 0
    for sx in (-1, 1):
        face = "-x" if sx > 0 else "+x"
        y = Y0 + rng.uniform(0, 6)
        while y < Y1:
            along = rng.uniform(14, 30)          # 通りに沿った長さ
            depth = rng.uniform(20, 32)          # 通りから奥への長さ
            cy = y + along / 2
            fh = rng.choice(FHS)
            base_fl = max(3, int(rng.uniform(18, 42) / fh))
            objs.append(more.tower(sx * (RW + depth / 2), cy, depth, along, base_fl,
                                   face, rng, idx, pitch=rng.choice(PITCHES), fh=fh))
            idx += 1
            # 上層: 通りから少し引いて、細く高く
            if rng.random() < 0.9:
                sb = rng.uniform(2.0, 7.0)
                d2 = depth * rng.uniform(0.55, 0.85)
                a2 = along * rng.uniform(0.6, 0.95)
                fh2 = rng.choice(FHS)
                objs.append(more.tower(sx * (RW + sb + d2 / 2), cy + rng.uniform(-1, 1),
                                       d2, a2, int(rng.uniform(85, 230) / fh2), face, rng, idx,
                                       pitch=rng.choice(PITCHES), fh=fh2))
                idx += 1
            y += along + rng.uniform(0.0, 2.5)
    return [o for o in objs if o is not None]


def stage():
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=1)
    ground = bpy.context.object
    ground.scale = (4000, 4000, 1)
    ground.location = (0, 200, -0.02)
    ground.name = "FP_ground"
    cd = bpy.data.cameras.new("C")
    cd.lens = 24.0
    cd.clip_start = 0.3
    cd.clip_end = 2000
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.0, -55.0, 2.2)
    cam.rotation_euler = (math.radians(93.5), 0.0, 0.0)
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.7, 0.7, 0.72, 1)
        bg.inputs[1].default_value = 0.6
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = math.radians(2.0)
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(58), 0, math.radians(-28))
    return ground


def grey(objs):
    m = bpy.data.materials.new("canyon_grey")
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (0.78, 0.78, 0.78, 1)
        b.inputs["Roughness"].default_value = 0.9
    for o in objs:
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(m)


def render(sc, name):
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    say(f"rendered {name}")


def prepare_scene():
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)
    rng = random.Random(SEED)
    towers = layout(rng)
    say(f"高層 {len(towers)} 棟")
    ground = stage()
    grey(towers + [ground])
    sc = bpy.context.scene
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = SAMPLES
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in towers + [ground]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = towers[0]
    return sc


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sc = prepare_scene()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "canyon_pre.blend"))
    faces = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    say(f"面 {faces:,}")
    if "--only-build" in ARGV:
        return
    # 手描き背景
    sc.fp_auto_style = "BACKGROUND"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    say(f"STEP0(手描き背景) 奥 {sc.fp_lw_far_start:.1f}..{sc.fp_lw_far_end:.1f} "
        f"密度 {sc.fp_lw_density:.3f} 減らし {sc.fp_lw_far_amount:.2f} 軽減 {sc.fp_lw_relief:.2f}")
    render(sc, "bg_relief1")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "canyon_bg.blend"))
    sc.fp_lw_far_amount = 0.0
    sc.fp_lw_relief = 0.0
    render(sc, "bg_relief0")
    # 精密(同じ形。STEP0 前から掛け直す)
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "canyon_pre.blend"))
    sc = bpy.context.scene
    sc.fp_auto_style = "PRECISE"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    render(sc, "precise")
    say("done")


if __name__ == "__main__":
    main()
