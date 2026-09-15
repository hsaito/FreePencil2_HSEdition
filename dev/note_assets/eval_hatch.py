"""陰影をハッチング(斜線の網)に置き換える実験。アドオンは触らない。

FreePencil の線画(強弱)と、同じカメラで撮った陰影(モノ光プレビュー)を
別々に出し、陰影の暗さを斜線の密度に変換して線画に重ねる。

    暗さ 0〜1 を 3 段の網で表す
      1段目  45度の斜線          暗さ > 0.30 で出る
      2段目  135度(交差)         暗さ > 0.55
      3段目  0度(さらに交差)     暗さ > 0.75
    段ごとに、線の太さは暗いほど太く(duty を暗さで動かす)

網の周期・角度・段数は引数で振れる。フルHD 200% で撮って 50% に落とす
(線画と同じ経路)。

  blender -b --factory-startup --python eval_hatch.py -- \
      [--model camera_2K] [--res 1920] [--period 14]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
MODEL = arg("--model", "camera_2K")
OUT = Path(arg("--out", str(HERE / "out" / f"hatch_{MODEL}"))).resolve()
RES_W = int(arg("--res", "1920"))
RES_H = RES_W * 9 // 16
PERIOD = float(arg("--period", "14"))      # 縮小後の画素で、斜線の間隔
SEG = float(arg("--seg", "90"))            # ストロークの長さ(px)
ROUGH = float(arg("--rough", "1.0"))       # 揺れと入り抜き。0 で縞
FRAMES = int(arg("--frames", "1"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W), "--ss", "1"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
import scan_models                # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)


def say(m):
    print(f"@@@ {m}", flush=True)


def load_rgba(path):
    img = bpy.data.images.load(str(path))
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, 4)[::-1].copy()      # 上が先頭に
    finally:
        bpy.data.images.remove(img)


def save_rgb(path, rgb):
    """0..1 の RGB(上が先頭)を PNG に。bpy は下が先頭なので反転して渡す"""
    h, w = rgb.shape[:2]
    img = bpy.data.images.new("hatch", w, h, alpha=True)
    rgba = np.concatenate([rgb, np.ones((h, w, 1), dtype=np.float32)], axis=2)
    img.pixels.foreach_set(rgba[::-1].astype(np.float32).ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


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
    from bpy_extras.object_utils import world_to_camera_view

    def place(d, ang):
        cam.location = (ctr.x + math.sin(ang) * d, ctr.y - math.cos(ang) * d,
                        ctr.z + d * 0.22)
        cam.rotation_euler = (ctr - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    d = r * 3.0
    for _ in range(3):
        place(d, math.radians(30))
        m = max(max(abs(world_to_camera_view(sc, cam, p).x - .5) * 2,
                    abs(world_to_camera_view(sc, cam, p).y - .5) * 2)
                for p in pts)
        d *= m * 1.10
    place(d, math.radians(30))
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
    lo.rotation_euler = (math.radians(55), 0, math.radians(35) + math.radians(30))
    return d, place


def _rand(*keys):
    """整数の組から 0..1 の擬似乱数(決定論的)。フレーム間で同じ値になる"""
    h = np.zeros_like(keys[0], dtype=np.float64)
    for i, k in enumerate(keys):
        h = h * 1013.0 + k.astype(np.float64) * (12.9898 + 7.7 * i)
    return np.abs(np.sin(h) * 43758.5453) % 1.0


def hatch(dark, period, layers, seg=90.0, gap=0.25, duty_lo=0.20,
          duty_hi=0.50, wobble=0.35, rough=1.0):
    """暗さ(0..1)を手描き風の斜線に。返り値はインク(0..1)。

    無限の縞ではなく、1本ずつ短いストロークを描く。
      - 長さ seg 前後(乱数で 0.6〜1.3 倍)、間に gap の隙間
      - 両端が細くなる(入り抜き)。太さは sin の山
      - 行の間隔と位置が少し揺れる(wobble)、行ごとに微妙に傾く
      - 暗いほど太く、暗さが薄れる所では細って消える
    rough=0 で揺れも入り抜きも無い縞に戻る。
    """
    h, w = dark.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    ink = np.zeros(dark.shape, dtype=np.float64)
    for li, (ang, start) in enumerate(layers):
        a = math.radians(ang)
        u = xx * math.cos(a) + yy * math.sin(a)        # 線に沿う
        v = -xx * math.sin(a) + yy * math.cos(a)       # 線に直交
        # 行(ストロークの列)。行ごとに位置と傾きを少し揺らす
        r = np.floor(v / period)
        jr = (_rand(r, np.full_like(r, li)) - 0.5) * period * 0.5 * rough
        tilt = (_rand(r, np.full_like(r, li + 7)) - 0.5) * 0.06 * rough
        vc = (r + 0.5) * period + jr + tilt * (u - w * 0.5)
        # 行ごとに沿う方向の位相をずらし、スロットに切る
        pr = _rand(r, np.full_like(r, li + 3)) * seg
        k = np.floor((u + pr) / seg)
        L = seg * (0.6 + 0.7 * _rand(r, k, np.full_like(r, li + 11)))  # 長さ
        s0 = _rand(r, k, np.full_like(r, li + 13)) * (seg - L * (1.0 - gap))
        t = ((u + pr) - (k * seg + s0)) / np.maximum(L, 1e-6)
        inside = (t > 0.0) & (t < 1.0)
        # 入り抜き: 両端で 0、中央で 1。少し非対称に(入りが速い)
        tt = np.clip(t, 0.0, 1.0)
        prof = np.sin(np.pi * tt) ** (0.55 if rough > 0 else 0.0)
        # 沿う方向の細かい揺れ
        wob = np.sin(u * 0.11 + _rand(r, k, np.full_like(r, li + 17)) * 6.28)             * period * 0.12 * wobble * rough
        # この層の強さ 0..1(start から +0.25 で 1 に)
        sdk = np.clip((dark - start) / 0.25, 0.0, 1.0)
        duty = duty_lo + (duty_hi - duty_lo) * sdk
        half = duty * 0.5 * period * prof * np.where(inside, 1.0, 0.0)
        # 暗さが薄れる所では細って消える(半幅を強さで縮める)
        half = half * (0.35 + 0.65 * sdk)
        d = np.abs(v - vc - wob)
        line = np.clip((half - d) + 0.75, 0.0, 1.0)      # 縁 1.5px ぼかし
        ink = np.maximum(ink, line * (sdk > 0.0))
    return ink.astype(np.float32)


def main():
    fp_batch.install_addon()
    from freepencil2 import fp_core
    path = next(m["path"] for m in scan_models.scan(scan_models.DEFAULT_ROOT)
                if MODEL in Path(m["path"]).stem)
    meshes, _ = dm.load(path)
    dm.grey(meshes)
    dist, place = stage(meshes)
    sc = bpy.context.scene
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view",
               "fp_auto_detect_aov", "fp_auto_white_preview"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.fp_auto_style = 'WEIGHTED'
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert sc.render.resolution_percentage == 200

    # 白 <-> モノ光を毎フレーム往復すると白に戻らなかった(実測: 2枚目
    # 以降の線画に陰影が乗った)。線画を全フレーム撮ってから、モノ光を
    # 全フレーム撮る
    def angle(f):
        return math.radians(30 + 360.0 * f / FRAMES) if FRAMES > 1 else math.radians(30)

    sc.fp_preview_mode = 'WHITE'
    for f in range(FRAMES):
        place(dist, angle(f))
        fp_batch.render_still(sc, OUT / f"f{f:03d}_line.png", 1)
    sc.fp_preview_mode = 'MONO_LIGHT'
    for f in range(FRAMES):
        place(dist, angle(f))
        fp_batch.render_still(sc, OUT / f"f{f:03d}_mono.png", 1)
    sc.fp_preview_mode = 'WHITE'

    from numpy.lib.stride_tricks import sliding_window_view
    variants = {
        "a_1layer": [(45, 0.30)],
        "b_2layer": [(45, 0.30), (135, 0.60)],
        "c_3layer": [(45, 0.25), (135, 0.50), (0, 0.75)],
    }
    for f in range(FRAMES):
        tag = f"f{f:03d}"
        line = load_rgba(OUT / f"{tag}_line.png")
        mono = load_rgba(OUT / f"{tag}_mono.png")
        alpha = line[..., 3]
        # 線画のインク(白地に黒線。透明は白)
        l_ink = (1.0 - line[..., :3].mean(axis=2)) * alpha
        # 陰影の暗さ。線の画素は陰影として数えない(線の分だけ暗く出るため)
        m_lum = mono[..., :3].mean(axis=2)
        dark = np.clip(1.0 - m_lum, 0.0, 1.0) * alpha
        dark = np.where(l_ink > 0.3, 0.0, dark)
        pad = np.pad(dark, 2, mode="edge")
        dark_s = sliding_window_view(pad, (5, 5)).mean(axis=(2, 3))
        # 暗さの目盛りを引き延ばす。モノ光は 0.25 が床なので、そこを 0 に
        dark_s = np.clip((dark_s - 0.10) / 0.65, 0.0, 1.0) * alpha
        for name, layers in variants.items():
            hk = hatch(dark_s, PERIOD, layers, seg=SEG, rough=ROUGH)
            ink = np.maximum(l_ink, hk * 0.75)
            save_rgb(OUT / f"{tag}_{name}.png", np.stack([1.0 - ink] * 3, axis=2))
        say(f"{tag} 完了")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
