"""水平線が何段も並ぶ面を、低い視点から真横に近い角度で見る試験場。

120m の通りの両側に、水平の線だけでできた壁(シャッターのスラット 8cm、
ベランダの手すり、ルーバー 15cm、サイディング 20cm、階の帯)を並べ、
カメラを高さ 30m(見下ろし)から 1.5m(壁と平行)まで下ろしていく。
奥ほど線が詰まってつぶれる条件を作り、つぶれ軽減の案を比べる。

  blender -b --factory-startup --python test_grazing.py -- --build [--out out/grazing]
      町を作って STEP0(手描き背景)まで掛けて保存
  blender -b --factory-startup --python test_grazing.py -- --stills --variants a,b --heights 30,12,5,1.5
      案ごとに静止画
  blender -b --factory-startup --python test_grazing.py -- --movie --variant a [--preview]
      カメラを下ろす動画(8 秒)
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
OUT = Path(arg("--out", str(HERE / "out" / "grazing"))).resolve()
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402
from town_kit import MB           # noqa: E402

L = 120.0          # 通りの長さ
HALF = 7.0         # 通りの半幅(壁の x)
FLOORS = 7
FH = 3.0
FRAMES = 192       # 8 秒


def wall(mb, side, rng_seed):
    """x = side*HALF の壁(正面は通り側)。水平の線だけを段々に重ねる。"""
    import random
    rng = random.Random(rng_seed)
    s = side
    x_face = s * HALF
    mb.box(x_face + s * 3.0, L / 2, FLOORS * FH / 2, 6.0, L, FLOORS * FH)     # 躯体
    out = -s                                                                  # 通り側へ
    # 1 階: シャッター(スラット 8cm)
    k = int(2.7 / 0.08)
    for i in range(k):
        mb.box(x_face + out * 0.05, L / 2, 2.7 - (i + 0.5) * 0.08, 0.03, L, 0.05)
    mb.box(x_face + out * 0.2, L / 2, 2.9, 0.4, L, 0.3)                      # シャッターボックス
    for fl in range(1, FLOORS):
        z0 = fl * FH
        mb.box(x_face + out * 0.05, L / 2, z0, 0.1, L, 0.14)                 # 階の帯
        kind = (fl + (0 if s > 0 else 1)) % 3
        if kind == 0:                                                         # ベランダ
            mb.box(x_face + out * 0.6, L / 2, z0 + 0.08, 1.2, L, 0.16)
            for zz in (0.35, 0.6, 0.85, 1.1):
                mb.box(x_face + out * 1.18, L / 2, z0 + zz, 0.05, L, 0.05)
        elif kind == 1:                                                       # ルーバー 15cm
            for i in range(int((FH - 0.4) / 0.15)):
                mb.box(x_face + out * 0.08, L / 2, z0 + 0.3 + i * 0.15, 0.12, L, 0.04)
        else:                                                                 # サイディング 20cm
            for i in range(int((FH - 0.3) / 0.2)):
                mb.box(x_face + out * 0.02, L / 2, z0 + 0.2 + i * 0.2, 0.04, L, 0.02)
    mb.box(x_face + out * 0.1, L / 2, FLOORS * FH + 0.3, 0.3, L, 0.6)         # パラペット
    for i in range(int(L / 12)):                                              # 縦の区切り(少し)
        mb.box(x_face + out * 0.1, 6 + i * 12, FLOORS * FH / 2, 0.2, 0.3, FLOORS * FH)


def build():
    fp_batch.install_addon()
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    objs = []
    for side, seed in ((1, 1), (-1, 2)):
        mb = MB(f"wall_{'R' if side > 0 else 'L'}")
        wall(mb, side, seed)
        objs.append(mb.build())
    mb = MB("ground_joints")                                                  # 歩道の目地(通りを横切る線)
    for sx in (-1, 1):
        mb.box(sx * (HALF - 1.5), L / 2, 0.075, 3.0, L, 0.15)
        for i in range(int(L / 0.9)):
            mb.box(sx * (HALF - 1.5), i * 0.9, 0.152, 2.9, 0.02, 0.006)
    objs.append(mb.build())
    bpy.ops.mesh.primitive_plane_add(size=1)
    ground = bpy.context.object
    ground.scale = (400, 400, 1)
    ground.location = (0, 60, -0.02)
    ground.name = "FP_ground"
    cd = bpy.data.cameras.new("C")
    cd.lens = 24.0
    cd.clip_start = 0.3
    cd.clip_end = 600
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    aim(cam, 1)
    lt = bpy.data.objects.new("K", bpy.data.lights.new("K", type="SUN"))
    lt.data.energy = 3.0
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(50), 0, math.radians(-35))
    w = bpy.data.worlds.new("W")
    sc.world = w
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 8
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.fps = 24
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs + [ground]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    sc.fp_auto_style = 'BACKGROUND'
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_mono_floor = 0.55
    sc.fp_preview_mode = 'MONO_LIGHT'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "grazing.blend"))
    print(f"@@@ built far {sc.fp_lw_far_start:.1f}..{sc.fp_lw_far_end:.1f}", flush=True)


def cam_at(h):
    """高さ h のカメラ。通りの中央、手前から奥を見る。高いほど見下ろす。"""
    pos = Vector((0.0, -4.0, h))
    tgt = Vector((0.0, 45.0, max(1.2, h * 0.25)))
    return pos, tgt


def aim(cam, f):
    t = (f - 1) / (FRAMES - 1)
    e = 0.5 - 0.5 * math.cos(t * math.pi)
    h = 30.0 + (1.5 - 30.0) * e
    pos, tgt = cam_at(h)
    cam.location = pos
    cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()


def apply_variant(sc, name):
    """案 = props の辞書(variants.json から読む)。STEP3 を作り直して反映。"""
    vs = json.loads((HERE / "grazing_variants.json").read_text(encoding="utf-8"))
    base = vs["_base"]
    for k, v in base.items():
        if k.startswith("fp_"):
            if hasattr(sc, k):
                setattr(sc, k, v)
            else:
                sc[k] = v
    for k, v in vs[name].items():
        if hasattr(sc, k):
            setattr(sc, k, v)
        else:
            sc[k] = v
    bpy.ops.freepencil2.link_button()
    # STEP3 を作り直すとプレビューの種類を掛け直す必要がある(白/モノクロ)
    mode = vs[name].get("fp_preview_mode", base.get("fp_preview_mode", "MONO_LIGHT"))
    sc.fp_preview_mode = "NONE"
    sc.fp_preview_mode = mode


def stills():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "grazing.blend"))
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = int(arg("--res", "1280")), int(arg("--res", "1280")) * 9 // 16
    sc.eevee.taa_render_samples = 4
    cam = sc.camera
    heights = [float(v) for v in arg("--heights", "30,12,5,1.5").split(",")]
    d = OUT / "stills"
    d.mkdir(parents=True, exist_ok=True)
    for name in arg("--variants").split(","):
        apply_variant(sc, name)
        for h in heights:
            pos, tgt = cam_at(h)
            cam.location = pos
            cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
            fp_batch.render_still(sc, d / f"{name}_h{h:g}.png", 1)
        print(f"@@@ {name}", flush=True)


def movie():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "grazing.blend"))
    sc = bpy.context.scene
    name = arg("--variant")
    apply_variant(sc, name)
    prev = "--preview" in ARGV
    sc.render.resolution_x = 960 if prev else 1920
    sc.render.resolution_y = sc.render.resolution_x * 9 // 16
    sc.eevee.taa_render_samples = int(arg("--samples", "4" if prev else "16"))
    cam = sc.camera
    for f in range(1, FRAMES + 1):
        aim(cam, f)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    sc.frame_start = int(arg("--start", "1"))
    sc.frame_end = int(arg("--end", str(FRAMES)))
    d = OUT / f"movie_{arg('--tag', name)}"
    d.mkdir(parents=True, exist_ok=True)
    sc.render.filepath = str(d / "f")
    bpy.ops.render.render(animation=True)
    print(f"@@@ movie {name}", flush=True)


if __name__ == "__main__":
    if "--build" in ARGV:
        build()
    elif "--stills" in ARGV:
        stills()
    elif "--movie" in ARGV:
        movie()
