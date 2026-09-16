"""遠景で線が密集して黒くなる所を軽減する案を、町のデモで総当りする(撮る側)。

町の .blend(make_town_demo.py が保存したもの)を開き、指定フレームで
「撮り直しが要る案」を1枚ずつ撮る。深度は EXR で一緒に出しておき、
後段(eval_far_ideas_post.py)で「深度を使う案」を合成して比べる。

撮る案(全部 実経路: 200% スーパーサンプル、強弱、モノ光の薄い陰影):
    base            今のまま
    relief05        遠景つぶれ軽減 0.5(半径6 しきい0.35)
    relief10        遠景つぶれ軽減 1.0
    relief10_wide   遠景つぶれ軽減 1.0(半径12 しきい0.25)
    relief03_tight  遠景つぶれ軽減 0.3(半径3 しきい0.5)
    sens            線の感度 1.8(線を減らす)
    thin            強弱OFF(精密と同じ細い線)
    thin_sens       強弱OFF + 感度1.8
    thin_sens3      強弱OFF + 感度3.0

  blender -b --python eval_far_ideas.py -- --blend out/town/town.blend \
      --out out/far_ideas [--frames 48,144] [--sens 1.8] [--only tag,tag]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "town" / "town.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "far_ideas"))).resolve()
FRAMES_TOTAL = int(arg("--total", "240"))
FRAMES = [int(x) for x in arg("--frames", "48,144").split(",")]
SENS = float(arg("--sens", "1.8"))

sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def aim(cam, f, length):
    """make_town_demo.aim と同じ動き"""
    t = f / max(FRAMES_TOTAL - 1, 1)
    yy = -6.0 + (length - 28.0) * t
    x = 0.4 * math.sin(t * math.pi * 2.0)
    cam.location = (x, yy, 1.6)
    yaw = math.radians(12.0) * math.sin(t * math.pi * 3.0)
    cam.rotation_euler = (math.radians(90.0), 0.0, yaw)
    bpy.context.view_layer.update()


def add_depth_output(sc, folder: Path):
    """コンポジタに深度の File Output を足す(STEP3 を押し直すと消える)"""
    from freepencil2 import compat
    tree = compat.get_compositor_tree(sc)
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    vl = sc.view_layers.get(rl.layer) or sc.view_layers[0]
    vl.use_pass_z = True
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.label = "FP_EVAL_DEPTH"
    fo.base_path = str(folder)
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.color_mode = "RGB"
    fo.file_slots[0].path = "z_"
    tree.links.new(rl.outputs["Depth"], fo.inputs[0])
    folder.mkdir(parents=True, exist_ok=True)
    return fo


def exr_to_npy(exr: Path, npy: Path):
    img = bpy.data.images.load(str(exr))
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        z = buf.reshape(h, w, 4)[::-1, :, 0].copy()   # 上が先頭になるよう反転
    finally:
        bpy.data.images.remove(img)
    np.save(npy, z)
    return z


def shoot(sc, cam, length, f, tag):
    aim(cam, f, length)
    sc.frame_set(f + 1)
    png = OUT / f"f{f:04d}_{tag}.png"
    fp_batch.render_still(sc, png, 1)
    say(f"  f{f:04d} {tag}")
    return png


def main():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    cam = sc.camera
    ground = bpy.data.objects["FP_ground"]
    length = ground.location.y * 2.0
    say(f"開いた 長さ{length:.1f} 強弱={sc.fp_line_weight} 仕上がり={sc.fp_auto_style} "
        f"陰影={sc.fp_preview_mode} 床={sc.fp_mono_floor:.2f} 200%={sc.render.resolution_percentage}")
    assert sc.render.resolution_percentage == 200
    info = {"frames": FRAMES, "sens": SENS, "length": length,
            "edges": [round(getattr(sc, f"fp_lw_e{i}"), 4) for i in range(1, 5)],
            "density": round(float(sc.fp_lw_density), 4)}

    only = [x for x in arg("--only", "").split(",") if x]
    # --- 今のまま + 深度
    if not only or "base" in only:
        fo = add_depth_output(sc, OUT / "depth")
        for f in FRAMES:
            shoot(sc, cam, length, f, "base")
            exr = OUT / "depth" / f"z_{f + 1:04d}.exr"
            z = exr_to_npy(exr, OUT / f"f{f:04d}_depth.npy")
            fin = z[z < 1e6]
            say(f"    深度 近{fin.min():.1f} 中央{np.median(fin):.1f} 遠{np.percentile(fin, 99):.1f}")
        from freepencil2 import compat
        compat.get_compositor_tree(sc).nodes.remove(fo)

    def want(tag):
        return not only or tag in only

    # --- 遠景つぶれ軽減(既存機能)
    for tag, s, r, t in (("relief05", 0.5, 6.0, 0.35), ("relief10", 1.0, 6.0, 0.35),
                         ("relief10_wide", 1.0, 12.0, 0.25),
                         ("relief03_tight", 0.3, 3.0, 0.5)):
        if not want(tag):
            continue
        sc.fp_far_relief_radius = r
        sc.fp_far_relief_threshold = t
        sc.fp_far_relief = s
        for f in FRAMES:
            shoot(sc, cam, length, f, tag)
    sc.fp_far_relief = 0.0

    # --- 線の感度(線を減らす)
    if want("sens"):
        sc.fp_line_sensitivity = SENS
        for f in FRAMES:
            shoot(sc, cam, length, f, "sens")
        sc.fp_line_sensitivity = 1.0

    # --- 強弱OFF(STEP3 を組み直す)
    sc.fp_line_weight = False
    bpy.ops.freepencil2.link_button()
    sc.fp_preview_mode = 'MONO_LIGHT'
    for tag, sv in (("thin", 1.0), ("thin_sens", SENS), ("thin_sens3", 3.0)):
        if not want(tag):
            continue
        sc.fp_line_sensitivity = sv
        for f in FRAMES:
            shoot(sc, cam, length, f, tag)

    if only:
        return
    (OUT / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
