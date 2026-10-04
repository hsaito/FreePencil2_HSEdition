"""峡谷の中をカメラが進むカットを撮る(STEP0 済みの canyon_bg.blend を使う)。

  blender -b --factory-startup --python render_canyon_move.py -- \
      [--blend out/canyon_dense/canyon_bg.blend] [--out out/canyon_dense/move]
      [--res 480] [--samples 4] [--frames 72] [--y0 -55] [--y1 -10]

出力は --res の 2 倍の大きさ(細線化の 200% レンダ。F12 と同じ)。
  move/r1/f0001.png ...  つぶれ軽減 ON(既定)
  move/r0/f0001.png ...  つぶれ軽減 OFF(「奥の線を控えめに」「つぶれ軽減」を 0)
STEP0 はやり直さない(距離としきい値は最初のカメラ位置で測った値のまま)。
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "canyon_dense" / "canyon_bg.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "canyon_dense" / "move"))).resolve()
RES = int(arg("--res", "480"))
SAMPLES = int(arg("--samples", "4"))
N = int(arg("--frames", "72"))
Y0 = float(arg("--y0", "-55"))
Y1 = float(arg("--y1", "-10"))
LENS = arg("--lens")      # 焦点距離を変えて撮る(望遠は遠景が画面の主役になる)
ONLY = {int(v) for v in arg("--only", "").split(",") if v}      # 1 始まりのコマ番号だけ撮る(確認用)
FAR_ON = float(arg("--far-on", "1.0"))     # ON 側の「奥の線を控えめに」(つぶれ軽減と重ねると遠景がにじむので 0 で撮る)
sys.path.insert(0, str(HERE.parent / "batch"))

import bpy          # noqa: E402
import fp_batch     # noqa: E402


def ease(t):
    return t * t * (3 - 2 * t)


def main():
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.eevee.taa_render_samples = SAMPLES
    cam = sc.camera
    if LENS:
        cam.data.lens = float(LENS)
    for tag, (far, relief) in (("r1", (FAR_ON, 1.0)), ("r0", (0.0, 0.0))):
        sc.fp_lw_far_amount = far
        sc.fp_lw_relief = relief
        d = OUT / tag
        d.mkdir(parents=True, exist_ok=True)
        for i in range(N):
            if ONLY and (i + 1) not in ONLY:
                continue
            t = i / max(1, N - 1)
            cam.location.y = Y0 + (Y1 - Y0) * ease(t)
            sc.render.filepath = str(d / f"f{i + 1:04d}.png")
            bpy.ops.render.render(write_still=True)
        print(f"@@@ {tag} {N} frames", flush=True)


main()
