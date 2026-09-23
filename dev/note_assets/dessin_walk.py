"""デッサン人形(Auto-Rig Pro)に歩きのアクションを作る。

脚と腕を FK に切り替え、1周 24 フレームの歩きを c_thigh_fk / c_leg_fk /
c_arm_fk / c_forearm_fk / c_root_master のキーで作る。軸は実測(回して
手先・足先の位置を読んだ):
  太もも 左 Z(+ で後ろ)  右 Z(+ で前)     膝 左 Z(+ で曲がる)  右 Z(- で曲がる)
  腕 左  X(+ で上がる) Z(+ で後ろ)   腕 右  X(+ で上がる) Z(+ で前)
  (右脚の軸は左と鏡。左と同じ符号にすると両脚が同じ向きに振れた)

単体で確かめる:
  blender -b --factory-startup --python dessin_walk.py -- --check [--out out/dessin/walk]
他のスクリプトからは make_walk(man_rig) を呼ぶ。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

CYCLE = 24                # 1周のフレーム数(1 秒)
STRIDE = 1.3              # 1周で進む距離(m)。2歩


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
    for f in range(0, CYCLE + 1, 2):
        p = 2 * math.pi * f / CYCLE
        for s, ph, arm_sign, leg_sign in (("l", 0.0, -1.0, 1.0), ("r", math.pi, 1.0, -1.0)):
            q = p + ph
            fwd = 24.0 * math.sin(q)                      # 太ももの前への振り
            knee = 4.0 + 50.0 * max(0.0, math.cos(q)) ** 1.5   # 振り出しの途中で最大
            _key(pb[f"c_thigh_fk.{s}"], f + 1, rot=(0.0, 0.0, -leg_sign * fwd))
            _key(pb[f"c_leg_fk.{s}"], f + 1, rot=(0.0, 0.0, leg_sign * knee))
            # 腕は下ろして、同じ側の脚と逆に振る
            swing = -16.0 * math.sin(q)                   # 腕の前への振り
            _key(pb[f"c_arm_fk.{s}"], f + 1, rot=(-72.0, 0.0, arm_sign * swing))
            _key(pb[f"c_forearm_fk.{s}"], f + 1, rot=(0.0, 0.0, arm_sign * (18.0 + 8.0 * max(0.0, math.sin(q)))))
        # 腰の上下: 脚が真下を通るとき高く、開いたとき低い(1周で2回)
        _key(pb["c_root_master.x"], f + 1, loc=(0.0, 0.0, -0.025 * abs(math.sin(p))))
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
        if not any(m.type == "CYCLES" for m in fc.modifiers):
            fc.modifiers.new("CYCLES")
    return act


def _check():
    ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    here = Path(__file__).resolve().parent
    out = Path(ARGV[ARGV.index("--out") + 1]) if "--out" in ARGV else here / "out" / "dessin" / "walk"
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(here / "out" / "dessin" / "dessin170_src.blend"))
    sc = bpy.context.scene
    arm = bpy.data.objects["man_rig"]
    make_walk(arm)
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
        for f in (1, 7, 13, 19):
            sc.frame_set(f)
            sc.render.filepath = str(out / f"{view}_f{f:02d}.png")
            bpy.ops.render.render(write_still=True)
    print(f"@@@ done {out}", flush=True)


if __name__ == "__main__" and "--check" in sys.argv:
    _check()
