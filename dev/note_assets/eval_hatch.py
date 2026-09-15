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
PROJ = arg("--proj", "sphere")             # surface=表面に貼る / sphere=包む球
SLIP = float(arg("--slip", "0.3"))         # 球がカメラの回転に追従する割合。0 で固定
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
    return d, place, ctr, r


def _rand(*keys):
    """整数の組から 0..1 の擬似乱数(決定論的)。フレーム間で同じ値になる"""
    h = np.zeros_like(keys[0], dtype=np.float64)
    for i, k in enumerate(keys):
        h = h * 1013.0 + k.astype(np.float64) * (12.9898 + 7.7 * i)
    return np.abs(np.sin(h) * 43758.5453) % 1.0


def hatch(dark, period, layers, seg=90.0, gap=0.25, duty_lo=0.20,
          duty_hi=0.50, wobble=0.35, rough=1.0, coords=None):
    """暗さ(0..1)を手描き風の斜線に。返り値はインク(0..1)。

    無限の縞ではなく、1本ずつ短いストロークを描く。
      - 長さ seg 前後(乱数で 0.6〜1.3 倍)、間に gap の隙間
      - 両端が細くなる(入り抜き)。太さは sin の山
      - 行の間隔と位置が少し揺れる(wobble)、行ごとに微妙に傾く
      - 暗いほど太く、暗さが薄れる所では細って消える
    rough=0 で揺れも入り抜きも無い縞に戻る。
    """
    h, w = dark.shape
    if coords is None:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    else:
        # 表面座標(画素の単位に直してある)。網が模型に貼り付く
        xx, yy = coords
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
    dist, place, ctr, rad = stage(meshes)
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

    # 表面座標(ワールド位置)と法線を EXR で出す。網を模型に貼り付けるため
    from freepencil2 import compat
    vl = bpy.context.view_layer
    vl.use_pass_position = True
    vl.use_pass_normal = True
    tree = compat.get_compositor_tree(sc)
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    fo = tree.nodes.new("CompositorNodeOutputFile")
    compat.file_output_set_dir(fo, str(OUT / "pass"))
    compat.file_output_clear_slots(fo)
    for name, sock in (("pos", "Position"), ("nrm", "Normal")):
        compat.file_output_add_slot(fo, name, "OPEN_EXR", "RGBA")
        tree.links.new(rl.outputs[sock], fo.inputs[name])
    try:
        fo.format.color_depth = "32"
    except (AttributeError, TypeError):
        pass
    # 線画は 200% のキャンバスいっぱいで出るので、パスも 200% のまま
    cams = []
    for f in range(FRAMES):
        place(dist, angle(f))
        cams.append(np.array(sc.camera.matrix_world.translation, dtype=np.float64))
        sc.frame_set(f + 1)
        bpy.ops.render.render(write_still=False)
    tree.nodes.remove(fo)

    # 画素1つがワールドで何単位か(55mm・36mm センサー・距離 dist)。
    # 絵は 200% のキャンバス(RES_W*2)で出る
    px_w = dist * 36.0 / 55.0 / (RES_W * 2)
    say(f"表面座標: 1px = {px_w:.4f} 単位")

    def load_exr(name, f):
        import glob
        p = sorted(glob.glob(str(OUT / "pass" / f"{name}*{f + 1:04d}*")))[0]
        img = bpy.data.images.load(p)
        try:
            w, h = img.size
            buf = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            # 線画も F12 は 200% のキャンバスいっぱい(3840)で出るので、
            # パスもそのまま使う
            return buf.reshape(h, w, 4)[::-1, :, :3].astype(np.float64)
        finally:
            bpy.data.images.remove(img)

    def surface_coords(f):
        """法線の向きで XY/YZ/ZX のどれかに投影し、画素の単位で返す"""
        P = load_exr("pos", f)
        N = load_exr("nrm", f)
        ax = np.argmax(np.abs(N), axis=2)
        cx = np.where(ax == 0, P[..., 1], np.where(ax == 1, P[..., 0], P[..., 0]))
        cy = np.where(ax == 0, P[..., 2], np.where(ax == 1, P[..., 2], P[..., 1]))
        # 面ごとに位相をずらして、面の境目で網がつながって見えないように
        cx = cx + ax * 37.0 * px_w
        return cx / px_w, cy / px_w

    def sphere_coords(f):
        """モデルを包む球にハッチングを貼り、カメラから見て合成する。

        表面にべったり貼ると傷に見える(指摘あり)。各画素の視線を球
        (中心=モデルの中心、半径=外接球の 1.3 倍)と交差させ、その交点の
        緯度経度でストロークを描く。球の表面は一様なので、面の向きや
        中心からの距離で網が圧縮されない。球はカメラの回転に SLIP の
        割合だけ追従させるので、網が面の上をゆっくり滑る
        """
        P = load_exr("pos", f)
        C = cams[f]
        O = np.array([ctr.x, ctr.y, ctr.z])
        Rb = rad * 1.3
        v = P - C
        v = v / np.maximum(np.linalg.norm(v, axis=2, keepdims=True), 1e-9)
        oc = C - O
        bq = np.einsum("ijk,k->ij", v, oc)
        cq = float(oc @ oc) - Rb * Rb
        disc = np.maximum(bq * bq - cq, 0.0)
        t = -bq - np.sqrt(disc)                  # 手前の交点
        q = C + v * t[..., None] - O
        q = q / Rb
        th = -(angle(f) - angle(0)) * SLIP
        c, s_ = math.cos(th), math.sin(th)
        x = q[..., 0] * c - q[..., 1] * s_
        y = q[..., 0] * s_ + q[..., 1] * c
        z = q[..., 2]
        lon = np.arctan2(y, x)
        lat = np.arcsin(np.clip(z, -1.0, 1.0))
        return lon * Rb / px_w, lat * Rb / px_w

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
        # 目盛り: 0.08 で 0、0.5 で 1。0.10/0.65 では網が 0.1% しか出なかった
        dark_s = np.clip((dark_s - 0.08) / 0.42, 0.0, 1.0) * alpha
        coords = sphere_coords(f) if PROJ == "sphere" else surface_coords(f)
        if f == 0:
            cx, cy = coords
            m = alpha > 0.5
            say(f"座標 x: {cx[m].min():.0f}..{cx[m].max():.0f}  y: {cy[m].min():.0f}..{cy[m].max():.0f}  "
                f"暗さ>0.3 の割合 {(dark_s[m] > 0.3).mean() * 100:.1f}%  rad {rad:.3f} px_w {px_w:.5f}")
            save_rgb(OUT / "dbg_dark.png", np.stack([1.0 - dark_s] * 3, axis=2))
        for name, layers in variants.items():
            hk = hatch(dark_s, PERIOD, layers, seg=SEG, rough=ROUGH, coords=coords)
            if f == 0:
                say(f"{name}: 網のインク {hk.mean() * 100:.2f}%  暗さ>0.3 {(dark_s > 0.3).mean() * 100:.2f}%")
            if f == 0 and name == "b_2layer":
                save_rgb(OUT / "dbg_hatch.png", np.stack([1.0 - hk] * 3, axis=2))
                hk_flat = hatch(np.ones_like(dark_s) * 0.9 * alpha, PERIOD, layers, seg=SEG, rough=ROUGH, coords=coords)
                save_rgb(OUT / "dbg_hatch_full.png", np.stack([1.0 - hk_flat] * 3, axis=2))
            ink = np.maximum(l_ink, hk * 0.75)
            save_rgb(OUT / f"{tag}_{name}.png", np.stack([1.0 - ink] * 3, axis=2))
        say(f"{tag} 完了")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
