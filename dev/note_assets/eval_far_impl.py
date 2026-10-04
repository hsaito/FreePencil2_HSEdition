"""奥の扱い(fp_lw_far / far_sens / far_fade)の実装を町の .blend で撮って確かめる。

eval_far_ideas.py の合成(width_sens3 / width_sens3_fade)と同じ絵に
なるかを、実装したノードで撮って並べる。

  blender -b --python eval_far_impl.py -- [--blend out/town/town.blend]
      [--out out/far_impl] [--frames 48,144] [--sets "1,3,0.35;1,3,0;1,1,0"]
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "town" / "town.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "far_impl"))).resolve()
FRAMES_TOTAL = int(arg("--total", "240"))
FRAMES = [int(x) for x in arg("--frames", "48,144").split(",")]
SETS = [tuple(float(v) for v in s.split(",")) for s in arg("--sets", "1,3,0.35;1,3,0;1,1,0").split(";")]

sys.path.insert(0, str(HERE.parent / "batch"))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def aim(cam, f, length):
    t = f / max(FRAMES_TOTAL - 1, 1)
    yy = -6.0 + (length - 28.0) * t
    x = 0.4 * math.sin(t * math.pi * 2.0)
    cam.location = (x, yy, 1.6)
    yaw = math.radians(12.0) * math.sin(t * math.pi * 3.0)
    cam.rotation_euler = (math.radians(90.0), 0.0, yaw)
    bpy.context.view_layer.update()


def main():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    cam = sc.camera
    length = bpy.data.objects["FP_ground"].location.y * 2.0
    # 距離はしきい値と一緒に測る(通りの真ん中で)
    aim(cam, FRAMES_TOTAL // 2, length)
    bpy.ops.freepencil.measure_line_weight()
    say(f"奥の距離 {sc.fp_lw_far_start:.1f} .. {sc.fp_lw_far_end:.1f}  "
        f"しきい値 {[round(getattr(sc, f'fp_lw_e{i}'), 4) for i in range(1, 5)]}")
    from freepencil2 import compat, line_weight
    for far, sens, fade in SETS:
        sc.fp_lw_far = far
        sc.fp_lw_far_sens = sens
        sc.fp_lw_far_fade = fade
        bpy.ops.freepencil2.link_button()
        sc.fp_preview_mode = 'MONO_LIGHT'
        tree = compat.get_compositor_tree(sc)
        taps = sorted({n.get("fp_tap") for n in tree.nodes if n.get("fp_tap")})
        gnode = next(n for n in tree.nodes if n.type == "GROUP")
        far_nodes = [n for n in gnode.node_tree.nodes if n.label == line_weight.FAR_LABEL]
        say(f"far={far} sens={sens} fade={fade}: taps {taps}  グループ内の挿し込み {len(far_nodes)}")
        tag = f"far{far:g}_sens{sens:g}_fade{fade:g}"
        for f in FRAMES:
            aim(cam, f, length)
            sc.frame_set(f + 1)
            fp_batch.render_still(sc, OUT / f"f{f:04d}_{tag}.png", 1)
            say(f"  f{f:04d} {tag}")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
