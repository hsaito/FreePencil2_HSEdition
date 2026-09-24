"""デッサン人形(Auto-Rig Pro)に歩きのアクションを作る。

脚と腕を FK に切り替え、歩行の角度曲線(股関節・膝、1周を 0..1 とした標準的な
歩行の値)からキーを打つ。軸は実測(回して手先・足先の位置を読んだ):
  太もも 左 Z(+ で後ろ)  右 Z(+ で前)     膝 左 Z(+ で曲がる)  右 Z(- で曲がる)
  (右脚の軸は左と鏡。左と同じ符号にすると両脚が同じ向きに振れた)
  腕  X(+ で上がる。-82 で体の横に下りる。-72 だと手が横に開き、-85 だと腰に付く)
      下ろした腕の前後の振りは Y(左は - で前、右は + で前)。以前は Z で振って
      いたが、下ろした腕では Z はねじれになり、振りが不自然だった(指摘あり)
  肘  Z(左は - で前へ曲がる、右は + で前へ)

以前の歩きは太ももを ±24 度の正弦で振っていて、後ろ脚が伸び切った大股
(突き出し)になった。歩行曲線に替えた。

進む速さは、立脚の足が地面を滑らないように実測して決める(measure_stride)。

単体で確かめる:
  blender -b --factory-startup --python dessin_walk.py -- --check [--out out/dessin/walk]
他のスクリプトからは make_walk(man_rig) を呼ぶ。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

CYCLE = 26                # 1周のフレーム数(24fps で 1.08 秒 = 1 分に 110 歩)
# 1周で進む距離(m)。立脚の足が滑らない値を measure_stride で測った
STRIDE = 1.00

# 歩行の角度曲線(左脚、t=0 がかかと接地)。度
#   股関節: + で前へ曲げる(屈曲)、- で後ろへ(伸展)
#   膝: + で曲げる
HIP = ((0.00, 24.0), (0.12, 20.0), (0.30, 4.0), (0.50, -10.0), (0.62, -8.0),
       (0.75, 12.0), (0.87, 27.0), (1.00, 24.0))
KNEE = ((0.00, 4.0), (0.12, 16.0), (0.30, 8.0), (0.45, 4.0), (0.60, 36.0),
        (0.72, 58.0), (0.85, 30.0), (0.97, 4.0), (1.00, 4.0))


def _curve(table, t):
    """周期的な折れ線を、なめらかにつないで読む(Catmull-Rom)。"""
    t = t % 1.0
    xs = [p[0] for p in table]
    ys = [p[1] for p in table]
    i = 0
    for i in range(len(xs) - 1):
        if xs[i] <= t <= xs[i + 1]:
            break
    n = len(xs) - 1                         # 最後の点は最初の点と同じ

    def y(k):
        return ys[k % n]
    p0, p1, p2, p3 = y(i - 1), y(i), y(i + 1), y(i + 2)
    u = (t - xs[i]) / max(xs[i + 1] - xs[i], 1e-6)
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * u * u * u)


def _key(pb, frame, rot=None, loc=None):
    if rot is not None:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = [math.radians(v) for v in rot]
        pb.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        pb.location = loc
        pb.keyframe_insert("location", frame=frame)


def make_walk(arm, name="Walk"):
    """arm(man_rig)に歩きのアクションを作って付ける。周期で回す。"""
    pb = arm.pose.bones
    for s in ("l", "r"):
        pb[f"c_foot_ik.{s}"]["ik_fk_switch"] = 1.0
        pb[f"c_hand_ik.{s}"]["ik_fk_switch"] = 1.0
    arm.animation_data_create()
    act = bpy.data.actions.new(name)
    arm.animation_data.action = act
    for f in range(0, CYCLE + 1):
        t = f / CYCLE
        for s, ph, leg_sign in (("l", 0.0, 1.0), ("r", 0.5, -1.0)):
            ts = t + ph
            hip = _curve(HIP, ts)
            knee = _curve(KNEE, ts)
            _key(pb[f"c_thigh_fk.{s}"], f + 1, rot=(0.0, 0.0, -leg_sign * hip))
            _key(pb[f"c_leg_fk.{s}"], f + 1, rot=(0.0, 0.0, leg_sign * knee))
            # 腕は体の横に下ろし、同じ側の脚と逆に前後へ振る(脚が前なら腕は後ろ)。
            # 前へは大きく、後ろへは小さく
            ph_arm = -hip / 27.0                      # + で腕が前
            swing = 15.0 * ph_arm if ph_arm > 0 else 8.0 * ph_arm
            fwd_sign = -1.0 if s == "l" else 1.0      # 前へ振る Y の符号
            _key(pb[f"c_arm_fk.{s}"], f + 1, rot=(-82.0, fwd_sign * swing, 0.0))
            elbow = 12.0 + 14.0 * max(0.0, ph_arm)    # いつも少し曲げ、前ほど深く
            _key(pb[f"c_forearm_fk.{s}"], f + 1, rot=(0.0, 0.0, fwd_sign * elbow))
        # 腰の上下: 立脚の真ん中(t=0.25, 0.75)で高く、両脚が開く接地で低い
        bob = -0.022 * (0.5 + 0.5 * math.cos(4 * math.pi * t))
        _key(pb["c_root_master.x"], f + 1, loc=(0.0, 0.0, bob))
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"            # 毎フレーム打っている
        if not any(m.type == "CYCLES" for m in fc.modifiers):
            fc.modifiers.new("CYCLES")
    return act


def measure_stride(arm):
    """立脚中に足が体に対して後ろへ動く距離から、1周で進む距離を測る。

    足が地面で止まって見えるには、体が(立脚中の足の後ろへの動き)と同じだけ
    前へ進めばよい。左足の t=0.05..0.45(かかと接地のあと〜蹴り出しの前)を読む。
    """
    sc = bpy.context.scene
    pb = arm.pose.bones

    def foot_y(frame):
        sc.frame_set(frame)
        return (arm.matrix_world @ pb["foot.l"].head).y
    f0 = 1 + round(0.05 * CYCLE)
    f1 = 1 + round(0.45 * CYCLE)
    back = foot_y(f1) - foot_y(f0)                  # 正面は -y なので後ろは +y
    return back / (f1 - f0) * CYCLE


def _check():
    ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    here = Path(__file__).resolve().parent
    out = Path(ARGV[ARGV.index("--out") + 1]) if "--out" in ARGV else here / "out" / "dessin" / "walk"
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(here / "out" / "dessin" / "dessin170_src.blend"))
    sc = bpy.context.scene
    arm = bpy.data.objects["man_rig"]
    make_walk(arm)
    stride = measure_stride(arm)
    print(f"@@@ 立脚の足が滑らない 1周の距離 {stride:.3f} m(STRIDE={STRIDE})", flush=True)
    from mathutils import Vector
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y = 640, 640
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    lt = bpy.data.objects.new("K", bpy.data.lights.new("K", type="SUN"))
    sc.collection.objects.link(lt)
    for view, loc in (("side", (5.0, 0.0, 0.9)), ("front", (0.0, -5.0, 0.9))):
        cd = bpy.data.cameras.new("C")
        cd.lens = 50
        cam = bpy.data.objects.new("C_" + view, cd)
        sc.collection.objects.link(cam)
        cam.location = loc
        cam.rotation_euler = (Vector((0, 0, 0.85)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.camera = cam
        for k in range(8):
            f = 1 + round(k * CYCLE / 8)
            sc.frame_set(f)
            sc.render.filepath = str(out / f"{view}_k{k}.png")
            bpy.ops.render.render(write_still=True)
    print(f"@@@ done {out}", flush=True)


if __name__ == "__main__" and "--check" in sys.argv:
    _check()
