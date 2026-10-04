"""スザンヌの耳の裏が「メカ塗り」になる理由を、塗りそのものを見て調べる。

線ではなく STEP1 の塗り分けを直接見る。頂点カラーを Attribute ->
Emission で素通しにしてレンダするので、線の検出を通さない生の色が出る。
CLAUDE.md の「塗り分けを触ったら素通しの画像で目で見る」に従う。

あわせて、耳の面がいくつの島に割れているか、その島が何面ずつかを出す。
1面や2面の島がぽつぽつ残っていれば、それが四角い継ぎ当てに見える。

  blender -b --factory-startup --python eval_ear_paint.py -- \
      --out <dir> [--res 1200]
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
OUT = Path(arg("--out", str(HERE / "out" / "ear_paint"))).resolve()
RES = int(arg("--res", "1200"))
SUBDIV = int(arg("--subdiv", "2"))
# 既定に任せるときは None。数値なら STEP0 のおすすめ設定を切って上書き
RIDGE = arg("--ridge")
MERGE = arg("--merge")

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES), "--ss", "1"]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)

# 耳のあたりを見る向き。真後ろ寄りと、真横
VIEWS = {"ear_back": (208.0, 12.0), "ear_side": (255.0, 6.0),
         "front": (20.0, 8.0)}


def say(m: str) -> None:
    print(f"@@@ {m}", flush=True)


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    if SUBDIV > 0:
        m = o.modifiers.new("Subdivision", "SUBSURF")
        m.levels = m.render_levels = SUBDIV
        bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    return o


def flat_material():
    """頂点カラーをそのまま出す。線の検出も陰影も通さない。"""
    mat = bpy.data.materials.new("FP_FlatPaint")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "mecha_color"
    em = nt.nodes.new("ShaderNodeEmission")
    ou = nt.nodes.new("ShaderNodeOutputMaterial")
    ou.location = (260, 0)
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
    return mat


def ear_faces(me):
    """耳の面の番号。スザンヌの耳は本体から離れた +-X の外れにある。"""
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)
    nf = len(me.polygons)
    cen = np.empty(nf * 3, dtype=np.float64)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(nf, 3)
    # |x| が大きく、体の中心より後ろ寄り。実測でスザンヌの耳は |x|>1.05
    return np.where(np.abs(cen[:, 0]) > 1.05)[0]


def main() -> None:
    fp_batch.install_addon()
    o = build()
    dm.grey([o])
    sc = bpy.context.scene

    # 出荷時の既定で通す
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    if RIDGE is not None or MERGE is not None:
        sc.fp_auto_merge = False
        if RIDGE is not None:
            sc.fp_ridge_amount = float(RIDGE)
        if MERGE is not None:
            sc.fp_min_island_area_pct = float(MERGE)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    me = o.data
    ears = ear_faces(me)
    say(f"耳の面 {len(ears)} / 全体 {len(me.polygons)}")

    # 面ごとの色をまとめて、耳の中に何色あるかを数える
    lay = me.color_attributes.get("mecha_color")
    nl = len(me.loops)
    c = np.empty(nl * 4, dtype=np.float32)
    lay.data.foreach_get("color", c)
    c = c.reshape(nl, 4)[:, :3]
    starts = np.empty(len(me.polygons), dtype=np.int32)
    totals = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    face_col = np.array([c[s:s + t].mean(axis=0)
                         for s, t in zip(starts, totals)])
    ear_col = np.round(face_col[ears], 3)
    uniq, counts = np.unique(ear_col, axis=0, return_counts=True)
    say(f"耳に出ている色 {len(uniq)}種")
    for col, n in sorted(zip(uniq.tolist(), counts.tolist()),
                         key=lambda x: -x[1]):
        say(f"   {n:5d}面  {col}")
    tiny = int(sum(n for n in counts if n <= 4))
    say(f"   4面以下の色が占める面 {tiny}面"
        f"  ({tiny / max(len(ears), 1) * 100:.1f}%)")

    # 塗りを素通しでレンダする
    mat = flat_material()
    keep = [s.material for s in o.material_slots]
    for s in o.material_slots:
        s.material = mat
    sc.use_nodes = False
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 16
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = True
    view = sc.view_settings.view_transform
    sc.view_settings.view_transform = "Standard"

    cd = bpy.data.cameras.new("C")
    cd.lens = 70.0
    cd.clip_end = 100
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    target = Vector((1.25, 0.0, 0.35))          # 耳のあたり
    for name, (az, el) in VIEWS.items():
        a = math.radians(az)
        e = math.radians(el)
        d = 2.4
        cam.location = (target.x + math.sin(a) * math.cos(e) * d,
                        target.y - math.cos(a) * math.cos(e) * d,
                        target.z + math.sin(e) * d)
        cam.rotation_euler = (target - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, OUT / f"{name}.png", 1)
        say(f"{name}.png")

    # 塗りを戻して、同じ向きで線画も撮る。塗りの色は最終的な線画には
    # 出ない(出るのは境界だけ)ので、そこを並べて確かめられるようにする
    sc.view_settings.view_transform = view
    for s, m in zip(o.material_slots, keep):
        s.material = m
    sc.use_nodes = True
    sc.fp_white_preview = True
    for name, (az, el) in VIEWS.items():
        a = math.radians(az)
        e = math.radians(el)
        d = 2.4
        cam.location = (target.x + math.sin(a) * math.cos(e) * d,
                        target.y - math.cos(a) * math.cos(e) * d,
                        target.z + math.sin(e) * d)
        cam.rotation_euler = (target - Vector(cam.location)).to_track_quat(
            "-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        fp_batch.render_still(sc, OUT / f"{name}_line.png", 1)
        say(f"{name}_line.png")
    (OUT / "ear.json").write_text(json.dumps(
        {"ear_faces": int(len(ears)), "colors": int(len(uniq)),
         "tiny_faces": tiny}, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
