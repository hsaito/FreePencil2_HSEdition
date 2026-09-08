"""透過テクスチャのあるモデルで輪郭線がどうなるかを調べる。

聞かれていること: アルファで抜いた葉っぱのようなカードに、線は
「板の四角い形」に出るのか「抜いたあとの見えている形」に出るのか。
そもそも出るのか。

制御された条件で見る。同じアルファ付きテクスチャを貼った板を4枚並べ、
ブレンド方式だけを変える。

  OPAQUE  透過を無視 = 四角い板のまま
  CLIP    しきい値で切り抜く
  HASHED  ディザで抜く(STEP0 が BLEND をここへ変換する)
  BLEND   そのまま半透明合成

さらに本物のガラス球を1つ置く。STEP0 の「BLEND→HASHED変換」は
ガラスを対象外にするので、そこが効いているかも同時に見える。

  blender -b --factory-startup --python eval_alpha.py -- \
      --fpbatch <リリースworktree>/dev/batch [--hashed 0]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


sys.path.insert(0, arg("--fpbatch",
                       str(Path(__file__).resolve().parents[1] / "batch")))
import fp_batch      # noqa: E402

OUT = Path(arg("--out", str(Path(__file__).resolve().parent / "out" / "alpha")))
OUT.mkdir(parents=True, exist_ok=True)
RES_W = int(arg("--res", "1600"))
RES_H = int(RES_W * 9 / 16)
AUTO_HASHED = bool(int(arg("--hashed", "1")))
TEX = OUT / "leaf_alpha.png"

MODES = ["OPAQUE", "CLIP", "HASHED", "BLEND"]


def make_texture(path: Path, size=512):
    """葉っぱ風のアルファを持つ PNG を作る。穴も開けて抜けを見る。

    Blender 同梱の Python には Pillow が無いので、先に外の Python で
    作っておく。既にあればそれを使う。
    """
    if path.exists():
        return path
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # 葉の輪郭(左右対称の紡錘形)
    pts = []
    for i in range(65):
        t = i / 64
        y = t * size
        w = math.sin(math.pi * t) ** 0.75 * size * 0.36
        pts.append((size / 2 - w, y))
    for i in range(64, -1, -1):
        t = i / 64
        y = t * size
        w = math.sin(math.pi * t) ** 0.75 * size * 0.36
        pts.append((size / 2 + w, y))
    d.polygon(pts, fill=(210, 215, 205, 255))
    # 葉脈のような穴を開ける(アルファの内側の境界を作る)
    for k in range(-4, 5):
        cy = size * (0.5 + k * 0.085)
        d.ellipse([size * 0.5 - 26, cy - 9, size * 0.5 + 26, cy + 9],
                  fill=(0, 0, 0, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def card(name, x, blend_mode, tex_path):
    bpy.ops.mesh.primitive_plane_add(size=1.6, location=(x, 0.0, 0.85),
                                     rotation=(math.radians(90), 0, 0))
    o = bpy.context.object
    o.name = name
    mat = bpy.data.materials.new(f"M_{name}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(str(tex_path))
    img.location = (-420, 0)
    nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(img.outputs["Alpha"], bsdf.inputs["Alpha"])
    mat.blend_method = blend_mode
    o.data.materials.append(mat)
    return o


def glass(x):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.45, location=(x, 0.0, 0.7),
                                         segments=48, ring_count=24)
    o = bpy.context.object
    o.name = "Glass"
    bpy.ops.object.shade_smooth()
    mat = bpy.data.materials.new("M_Glass")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    tr = b.inputs.get("Transmission Weight") or b.inputs.get("Transmission")
    if tr is not None:
        tr.default_value = 1.0
    mat.blend_method = "BLEND"
    o.data.materials.append(mat)
    return o


def stage(objs):
    """全部が枠に収まる距離を、実際の広がりから出す。

    決め打ちの距離だと端が切れる(最初に左端のカードが見切れた)。
    """
    sc = bpy.context.scene
    lens = 50.0
    xs, zs = [], []
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            xs.append(w.x)
            zs.append(w.z)
    half_w = (max(xs) - min(xs)) * 0.5 * 1.10
    half_h = (max(zs) - min(zs)) * 0.5 * 1.10
    cz = (max(zs) + min(zs)) * 0.5
    sensor_w = 36.0
    sensor_h = sensor_w * RES_H / RES_W
    d = max(half_w / math.tan(math.atan(sensor_w * 0.5 / lens)),
            half_h / math.tan(math.atan(sensor_h * 0.5 / lens)))
    cd = bpy.data.cameras.new("C")
    cd.lens = lens
    cd.clip_end = d * 20
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.0, -d, cz)
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.52, 0.53, 0.56, 1.0)
        bg.inputs[1].default_value = 0.8
    sc.world = w
    lt = bpy.data.lights.new("Key", type="AREA")
    lt.energy, lt.size = 900.0, 6.0
    lo = bpy.data.objects.new("Key", lt)
    sc.collection.objects.link(lo)
    lo.location = (2.0, -4.0, 4.0)
    lo.rotation_euler = (math.radians(35), 0, math.radians(28))


def main():
    fp_batch.install_addon()
    bpy.ops.wm.read_homefile(use_empty=True)
    tex = make_texture(TEX)

    objs = []
    xs = [(i - (len(MODES)) / 2.0) * 1.9 for i in range(len(MODES) + 1)]
    for i, m in enumerate(MODES):
        objs.append(card(m, xs[i], m, tex))
    objs.append(glass(xs[-1]))
    stage(objs)

    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = False
    sc.fp_auto_hashed = AUTO_HASHED

    before = {o.name: o.data.materials[0].blend_method for o in objs}
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    after = {o.name: o.data.materials[0].blend_method for o in objs}

    print(f"@@@ BLEND→HASHED変換 = {'ON' if AUTO_HASHED else 'OFF'}", flush=True)
    for o in objs:
        b, a = before[o.name], after[o.name]
        mark = "  <- 変換された" if b != a else ""
        print(f"@@@   {o.name:<8} {b:>7} -> {a:<7}{mark}", flush=True)

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x, sc.render.resolution_y = RES_W, RES_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    tag = "hashed_on" if AUTO_HASHED else "hashed_off"
    fp_batch.render_still(sc, OUT / f"{tag}_line.png", 1)
    sc.use_nodes = False
    fp_batch.render_still(sc, OUT / f"{tag}_plain.png", 1)
    sc.use_nodes = True
    from bpy_extras.object_utils import world_to_camera_view
    import json
    marks = {}
    for o in objs:
        co = world_to_camera_view(sc, sc.camera, o.matrix_world.translation)
        marks[o.name] = [round(co.x * RES_W), round((1 - co.y) * RES_H)]
    (OUT / f"{tag}_marks.json").write_text(
        json.dumps({"size": [RES_W, RES_H], "marks": marks,
                    "blend": {k: v for k, v in after.items()}},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{tag}.blend"))
    print(f"@@@ 完了 {OUT}", flush=True)


if __name__ == "__main__":
    main()
