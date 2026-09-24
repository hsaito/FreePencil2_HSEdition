"""町 v2 を映画的なカメラワークで 30 秒撮る(3 カット、車が走る)。

  カット A (0-8s)   横断歩道のローアングル。車が手前を横切り、カメラは
                    ゆっくり持ち上がりながら通りの奥を向く
  カット B (8-19s)  4m の高さで通りをドリー。走る車を追い、看板と電線の
                    間を抜ける
  カット C (19-30s) 交差点の真ん中で 360 度回る(目の高さ、車がすぐ横を通る)

  blender -b --factory-startup --python shoot_town_v2.py -- \
      [--blend out/town_v2/town.blend] [--out out/town_v2/shot] [--frames 720]
      [--only-frames 60,300,600]   経路の確認用(その番号だけ撮る)
      [--preview]                  960x540・4サンプルで全フレーム(動きの確認、約 15 分)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "town_v2" / "town.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "town_v2" / "shot"))).resolve()
FRAMES = int(arg("--frames", "720"))
ONLY = [int(v) for v in arg("--only-frames", "").split(",") if v]
START = int(arg("--start", "1"))     # このフレームから撮る(カットの撮り直し用)
PREVIEW = "--preview" in ARGV        # 低解像度・少サンプルで動きだけ確かめる
RES = int(arg("--res", "960" if PREVIEW else "1920"))
SAMPLES = int(arg("--samples", "4" if PREVIEW else "16"))
FPS = 24

sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)

ROAD = 5.5
CUTS = (0.0, 8.0, 19.0, 30.0)     # 秒


def ease(t):
    return 0.5 - 0.5 * math.cos(max(0.0, min(1.0, t)) * math.pi)


def look(cam, pos, target, roll=0.0):
    cam.location = pos
    q = (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y")
    e = q.to_euler()
    e.rotate_axis("Z", 0.0)
    cam.rotation_euler = e
    if roll:
        cam.rotation_euler.rotate_axis("Z", roll)


def shot_a(s, cam):
    """横断歩道の脇、地上 0.5m。手前を車が横切る。"""
    e = ease(s)
    # y=-14 と -32 に街路樹があるので、その間から
    pos = (ROAD - 0.4 - 0.8 * e, -26.0 + 5.0 * e, 0.6 + 1.2 * e)
    tgt = (-2.0 + 2.0 * e, 4.0 + 70.0 * e, 1.0 + 1.6 * e)
    cam.data.lens = 24.0
    look(cam, pos, tgt)


def shot_b(s, cam):
    """通りの上をドリー(y: 10 -> 58)。少し右へ振る。"""
    e = ease(s)
    y = 10.0 + 48.0 * s
    pos = (-1.2 + 0.8 * math.sin(s * math.pi), y, 3.6 + 0.6 * e)
    tgt = (1.2 + 1.5 * math.sin(s * math.pi * 0.5), y + 26.0, 2.2)
    cam.data.lens = 35.0
    look(cam, pos, tgt)


def shot_c(s, cam):
    """交差点の真ん中で 360 度回る。

    目の高さ(1.6m)で、通りの先(北)から始めて時計回りに一周。走る車が
    すぐ横を通り過ぎる。回転は始めと終わりを緩め、少しだけ上がる。
    """
    e = ease(s)
    cx, cy = 0.0, 64.0
    yaw = math.radians(360.0 * e)
    z = 1.6 + 0.8 * e
    pos = (cx, cy, z)
    tgt = (cx + 20.0 * math.sin(yaw), cy + 20.0 * math.cos(yaw), z + 0.6 - 0.4 * e)
    cam.data.lens = 24.0
    look(cam, pos, tgt)


def aim(cam, f):
    t = f / FPS
    for k in range(3):
        if t < CUTS[k + 1] or k == 2:
            s = (t - CUTS[k]) / (CUTS[k + 1] - CUTS[k])
            (shot_a, shot_b, shot_c)[k](min(1.0, s), cam)
            return


def spin_wheels(car, dist, f0, f1):
    """車輪(子の wheel_*)を進んだ距離ぶん回す。角度 = 距離 / 半径。

    車の正面は -y、車輪の軸は車の x。前へ進むとき +x 回りに回すと、
    タイヤの上側が前(-y)へ動く。
    """
    for w in car.children:
        if not w.name.startswith("wheel_"):
            continue
        r = float(w.get("fp_r", 0.3)) * car.matrix_world.to_scale().x
        # 本当の転がりは 9m/s・半径0.34m で1コマ63度。5本スポークは72度ごとに同じ
        # 形なので、24fps では止まって見えるか逆回りに見える(車輪の錯覚)。
        # 1コマ 25 度までに抑える(遅めだが前へ回って見える)
        per_frame = min(dist / max(r, 1e-3) / max(f1 - f0, 1), math.radians(25.0))
        base = w.rotation_euler.x
        w.rotation_euler.x = base
        w.keyframe_insert("rotation_euler", index=0, frame=f0)
        w.rotation_euler.x = base + per_frame * (f1 - f0)
        w.keyframe_insert("rotation_euler", index=0, frame=f1)
        for fc in w.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def moving_cars(sc):
    """走る車: 大通りの車線にいる車を全部走らせる(止まった車と重ならないように)。

    半分を止めておくと、走る車が止まった車に重なった(実測)。車線の車は
    全部同じ速さで走らせ(追い越しが無いので重ならない)、横切る車が
    交差点を通る 2〜5.5 秒の間に交差点(y -8..4)へ来る車は手前へずらす。
    """
    cars = [o for o in sc.objects if o.type == "MESH" and o.name.startswith("asset_")
            and any(k in o.name for k in ("police", "toyota", "lancia", "hyundai", "audi", "mclaren"))
            and not o.hide_viewport and abs(o.matrix_world.translation.x) < ROAD]
    moved = 0
    for o in cars:
        x = o.matrix_world.translation.x
        speed = 9.0 if x < 0 else -8.0          # m/s。x<0 は北向き(左側通行、正面は +y に回してある)
        y0 = o.matrix_world.translation.y
        # 横切る車が交差点を通る間(2〜5.5秒)に交差点へ来る車は外す
        # (ずらすと隣の車に重なる)
        if any(-8.0 < y0 + speed * t < 4.0 for t in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5)):
            for ob in [o] + list(o.children):        # 車輪も一緒に消す
                ob.hide_render = True
                ob.hide_viewport = True
            continue
        for f in (1, FRAMES):
            o.location.y = y0 + speed * (f - 1) / FPS
            o.keyframe_insert("location", frame=f)
        if o.animation_data and o.animation_data.action:
            for fc in o.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
        spin_wheels(o, abs(speed) * (FRAMES - 1) / FPS, 1, FRAMES)
        moved += 1
    # カット A で手前を横切る車を 1 台、横町に置いて走らせる
    if cars:
        src = cars[0]
        c = src.copy()
        sc.collection.objects.link(c)
        # copy() はアクションを共有する。そのままキーを打つと元の車も同じ
        # 経路を走り、2台が同じ場所に重なった(実測: 3秒の交差点)
        c.animation_data_clear()
        for w in [w for w in src.children if w.name.startswith("wheel_")]:
            wc = w.copy()                            # 車輪も付け替える(子は copy されない)
            sc.collection.objects.link(wc)
            wc.animation_data_clear()
            wc.parent = c
            wc.hide_render = wc.hide_viewport = False
        c.rotation_euler = (0, 0, math.radians(-90))     # 正面(-y)を -x へ
        # 高さは元の車のまま。0 にすると町 v4(車道の面が高い)で車輪が
        # 道に半分沈んだ(デモの 7 秒目)
        z0 = src.matrix_world.translation.z
        for f, x in ((1, 22.0), (int(8 * FPS), -26.0)):
            c.location = (x, -2.6, z0)
            c.keyframe_insert("location", frame=f)
        for fc in c.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        spin_wheels(c, 48.0, 1, int(8 * FPS))
        moved += 1
    return moved


def main():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    cam = sc.camera
    sc.render.fps = FPS
    n = moving_cars(sc)
    print(f"@@@ 走る車 {n} 台", flush=True)
    if ONLY:
        if PREVIEW or "--res" in ARGV:   # 経路の確認・撮り直しでも本番と同じ大きさで撮る
            sc.render.resolution_x = RES
            sc.render.resolution_y = RES * 9 // 16
            sc.eevee.taa_render_samples = SAMPLES
        for f in ONLY:
            aim(cam, f)
            sc.frame_set(f + 1)
            fp_batch.render_still(sc, OUT / f"f{f:04d}.png", 1)
            print(f"@@@ f{f:04d}", flush=True)
        return
    for f in range(FRAMES):
        aim(cam, f)
        cam.keyframe_insert("location", frame=f + 1)
        cam.keyframe_insert("rotation_euler", frame=f + 1)
        cam.data.keyframe_insert("lens", frame=f + 1)
    # カットの境目は補間せず飛ぶ(1フレームで切り替わるので線形でも同じ)
    sc.frame_start, sc.frame_end = START, FRAMES
    sc.render.filepath = str(OUT / "f")
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.eevee.taa_render_samples = SAMPLES
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT.parent / "town_shot.blend"))
    bpy.ops.render.render(animation=True)
    print(f"@@@ 完了 {OUT}", flush=True)


if __name__ == "__main__":
    main()
