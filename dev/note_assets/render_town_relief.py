"""保存済みの町から、遠景つぶれ軽減の効き比べを撮る。

make_town_movie.py は毎回 BlenderKit のアセットを探して町を組み直すが、
索引の名前が今のライブラリと合わなくなっていて、建物が1つも配置されない
(実際に「配置 0」の空の絵が96枚出た)。組み直さず、以前うまく組めた
out/town/town.blend をそのまま開いて、軽減の値だけ変えて撮る。

カメラは向こうのスクリプトがキーフレームを打ってあるので、
frame_set で進めればドリーがそのまま再現される。

  blender -b --factory-startup --python render_town_relief.py -- \
      --blend out/town/town.blend --out <dir> --relief 0.6 \
      [--frames 96] [--res 1280] [--ss 2]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


BLEND = Path(arg("--blend", str(HERE / "out" / "town" / "town.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "town_relief"))).resolve()
RELIEF = float(arg("--relief", "0.6"))
FRAMES = int(arg("--frames", "96"))
RES = int(arg("--res", "1280"))
SS = int(arg("--ss", "2"))
T0 = time.time()


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def main() -> None:
    fp_batch.install_addon()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]
    say(f"{BLEND.name}: メッシュ {len(meshes)}")
    if len(meshes) < 10:
        raise SystemExit("町が入っていない。別の .blend を指定すること")

    from freepencil2 import fp_core
    scene.fp_far_relief = RELIEF
    groups = [g for g in bpy.data.node_groups
              if g.name.startswith(fp_core.NODE_GROUP_PREFIX)]
    for ng in groups:
        fp_core.far_relief_from_scene(ng, scene)
    say(f"遠景つぶれ軽減 {scene.fp_far_relief} をノードグループ {len(groups)} 個へ")

    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    # この .blend は 960x540 の 200% で保存されていて、コンポジタ側にも
    # アドオンの細線化(2倍で描いて 0.5 に縮める Scale ノード)が入っている。
    # そこへ render_still の縮小を重ねると、絵ごと枠の中で小さくなる
    # (実際にそうなった)。同じ関係を保ち、縮小はコンポジタ任せにする
    scene.render.resolution_percentage = 200
    scene.render.resolution_x = RES
    scene.render.resolution_y = int(RES * 9 / 16)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    d = OUT / "frames"
    d.mkdir(parents=True, exist_ok=True)
    n = min(FRAMES, scene.frame_end - scene.frame_start + 1)
    t = time.time()
    for i in range(n):
        scene.frame_set(scene.frame_start + i)
        fp_batch.render_still(scene, d / f"f{i + 1:04d}.png", 1)
        if (i + 1) % 20 == 0 or i + 1 == n:
            say(f"  {i + 1}/{n} フレーム ({time.time() - t:.0f}s)")
    say(f"完了 {d}")


if __name__ == "__main__":
    main()
