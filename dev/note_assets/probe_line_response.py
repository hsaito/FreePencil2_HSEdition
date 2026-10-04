"""どの色差なら線が出るのかを、平面の格子で直接見る。

FreePencil の塗り分け(STEP1)は使わない。自前で既知の色を格子の各セルに
置き、STEP2/STEP3 だけ通してレンダする。平面なので二面角はどこもゼロ、
深度も一定。つまり **線が出るとしたら色チャンネルだけが理由**になる。
検出器の応答を単独で切り出せる。

線の検出は「白背景にプリミックス -> Sobel -> ColorRamp(輝度)」なので、
出るかどうかは輝度勾配がしきい値を超えるかで決まる。RGB距離が大きくても
輝度が近ければ出ない、という仮説をここで確かめる。

行 = 色差の種類、列 = 差の大きさ。列が右へ行くほど隣との差が開く。
どの列から線が出始めるかを見る。

    blender -b --factory-startup --python probe_line_response.py -- \
        [--cols 12] [--res 1600]
"""
from __future__ import annotations

import colorsys
import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "line_response"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
COLS = int(arg("--cols", "12"))
RES = int(arg("--res", "1600"))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# 行の定義。(名前, セル色を返す関数)
# t は 0..1 で列の位置。隣の列との差が「差の大きさ」になる。
def _hsv(h, s, v):
    return colorsys.hsv_to_rgb(h % 1.0, s, v)


def row_luma(t):
    """明度だけ動かす(無彩色)。輝度差そのもの。"""
    v = 0.25 + 0.60 * t
    return (v, v, v)


def row_hue(t):
    """色相だけ動かす。輝度はほぼ一定に保つ。"""
    r, g, b = _hsv(t, 0.85, 0.75)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    k = 0.55 / max(lum, 1e-6)
    return tuple(min(1.0, c * k) for c in (r, g, b))


def row_sat(t):
    """彩度だけ動かす。"""
    return _hsv(0.08, t, 0.75)


def row_palette(t):
    """実際に使われているパレットの色を順に並べる。"""
    from freepencil2 import utils
    pal, _d, _l = utils.build_palette(COLS, 42)
    i = min(COLS - 1, int(round(t * (COLS - 1))))
    return tuple(pal[i])


def row_luma_fine(t):
    """明度を細かく動かす。どこから線が出るかの下限を見る。"""
    v = 0.50 + 0.14 * t
    return (v, v, v)


def _steps(n, lo, hi):
    """境界ごとに差を変える。左から右へ差が広がる。"""
    return [lo + (hi - lo) * (i / max(n - 2, 1)) for i in range(n - 1)]


# 差を累積させると右端で上限に張り付き、差がゼロになって線が消える。
# 中央値の上下へ交互に振れば、どこまで行っても飽和しない。
# 境界 i がテストする差は d[i] とほぼ等しくなる。
def _alt(n, lo, hi, mid, make):
    d = [lo + (hi - lo) * (i / max(n - 1, 1)) for i in range(n)]
    out = [make(mid + (d[i] * 0.5 if i % 2 == 0 else -d[i] * 0.5))
           for i in range(n)]
    st = [(d[i] + d[i + 1]) * 0.5 for i in range(n - 1)]
    return out, st


def sweep_luma(n, lo=0.002, hi=0.14):
    """明度差の掃引。無彩色なので輝度差そのもの。"""
    return _alt(n, lo, hi, 0.55, lambda v: (v, v, v))


def sweep_hue(n, lo=0.004, hi=0.30):
    """色相差の掃引。輝度は 0.55 に揃える。"""
    def make(h):
        r, g, b = _hsv(h, 0.85, 0.9)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        k = 0.55 / max(lum, 1e-6)
        return tuple(min(1.0, c * k) for c in (r, g, b))
    return _alt(n, lo, hi, 0.35, make)


def sweep_sat(n, lo=0.01, hi=0.60):
    return _alt(n, lo, hi, 0.5, lambda s: _hsv(0.08, max(0.0, min(1.0, s)), 0.8))


def seq_palette(n):
    """パレットをクラス番号順に並べる(=隣接に割り当てられる順)。"""
    from freepencil2 import utils
    pal, _d, _l = utils.build_palette(n, 42)
    return [tuple(c) for c in pal], None


def seq_palette_shuffled(n):
    """パレットを離れた番号同士が隣り合う順に並べる。

    彩色は「隣は違うクラス」しか保証しない。離れたクラス同士が画面で
    隣り合ったとき線が出るかを見る。
    """
    from freepencil2 import utils
    pal, _d, _l = utils.build_palette(n, 42)
    order = [(i * 5 + 2) % n for i in range(n)]
    return [tuple(pal[i]) for i in order], None


ROWS = [
    ("明度差の掃引 0.004 → 0.10", sweep_luma),
    ("色相差の掃引 (輝度0.55固定)", sweep_hue),
    ("彩度差の掃引", sweep_sat),
    ("パレット(クラス番号順)", seq_palette),
    ("パレット(離れた番号が隣)", seq_palette_shuffled),
]


def build_grid():
    """列 COLS x 行 len(ROWS) の格子平面を作り、面ごとに色を置く。"""
    nx, ny = COLS, len(ROWS)
    # セルを正方形にする。平面を 1:1 で作ると 12列x5行が画角から外れる
    h = ny / nx
    verts, faces = [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            verts.append((i / nx - 0.5, 0.0, h * (0.5 - j / ny)))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    me = bpy.data.meshes.new("GRID")
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new("GRID", me)
    bpy.context.scene.collection.objects.link(obj)

    # 面 -> 色。左上が (行0, 列0)
    cols = np.zeros((len(me.polygons), 3), dtype=np.float64)
    info = []
    for j, (name, fn) in enumerate(ROWS):
        seq, steps = fn(nx)
        for i in range(nx):
            cols[j * nx + i] = seq[i]
        # 境界ごとの実際の輝度差とRGB距離を控える(画像の目盛りとして使う)
        lum = [0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] for c in seq]
        bnd = []
        for i in range(nx - 1):
            a, b = np.array(seq[i]), np.array(seq[i + 1])
            bnd.append({"i": i,
                        "dluma": round(abs(lum[i + 1] - lum[i]), 4),
                        "drgb": round(float(np.linalg.norm(b - a)), 4),
                        "step": round(steps[i], 4) if steps else None})
        info.append({"row": name,
                     "colors": [[round(v, 4) for v in c] for c in seq],
                     "boundaries": bnd})

    attr = me.color_attributes.new(name="mecha_color", type='BYTE_COLOR',
                                   domain='CORNER')
    buf = np.zeros(len(me.loops) * 4, dtype=np.float32)
    for p in me.polygons:
        c = cols[p.index]
        for li in range(p.loop_start, p.loop_start + p.loop_total):
            buf[li * 4:li * 4 + 3] = c
            buf[li * 4 + 3] = 1.0
    attr.data.foreach_set("color", buf)
    # 他のチャンネルは使わないが、ノードが参照するので空で用意する
    for extra in ("bone_color", "mask_color", "line_color"):
        a2 = me.color_attributes.new(name=extra, type='BYTE_COLOR',
                                     domain='CORNER')
        b2 = np.zeros(len(me.loops) * 4, dtype=np.float32)
        b2[3::4] = 1.0
        a2.data.foreach_set("color", b2)
    me.color_attributes.active_color = attr

    mat = bpy.data.materials.new("GRID_MAT")
    mat.use_nodes = True
    me.materials.append(mat)
    say(f"格子 {nx}列 x {ny}行 = {len(me.polygons)}面")
    return obj, info


def add_camera():
    cd = bpy.data.cameras.new("Cam")
    cd.type = 'ORTHO'
    # 平面の幅ちょうど。余白を入れるとセル境界の画素位置がずれて、
    # 「どの境界に線が出たか」を画像から読み取れなくなる
    cd.ortho_scale = 1.0
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = (0.0, 3.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0.0, math.radians(180))


def render_vc(scene, png):
    """頂点カラーを素通しで描く(置いた色そのもの)。"""
    mat = bpy.data.materials.new("VC")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "mecha_color"
    em = nt.nodes.new("ShaderNodeEmission")
    ou = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
    obj = bpy.data.objects["GRID"]
    keep = [s.material for s in obj.material_slots]
    for s in obj.material_slots:
        s.material = mat
    kc, kv = scene.use_nodes, scene.view_settings.view_transform
    scene.use_nodes = False
    scene.view_settings.view_transform = 'Standard'
    fp_batch.render_still(scene, png, 1)
    scene.use_nodes, scene.view_settings.view_transform = kc, kv
    for s, m in zip(obj.material_slots, keep):
        s.material = m


def main():
    fp_batch.install_addon()
    from freepencil2 import fp_core
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    vl = bpy.context.view_layer

    obj, info = build_grid()
    add_camera()

    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'NONE'
    scene.fp_auto_supersample = False
    scene.fp_supersample = False

    # STEP1(塗り分け)は通さない。色は自分で置いてある
    fp_core.setup_aov(scene, vl)
    fp_core.setup_compositor(scene, vl)
    say("STEP2/STEP3 のみ適用(塗り分けは自前)")

    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 8
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = RES
    scene.render.resolution_y = int(RES * len(ROWS) / COLS)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    line_png = OUT / "line.png"
    fp_batch.render_still(scene, line_png, 1)
    say(f"線画 {line_png}")

    vc_png = OUT / "colors.png"
    render_vc(scene, vc_png)
    say(f"置いた色 {vc_png}")

    blend = OUT / "line_response.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    say(f"保存 {blend}")

    (OUT / "grid.json").write_text(
        json.dumps({"cols": COLS, "rows": info}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    say("完了")


if __name__ == "__main__":
    main()
