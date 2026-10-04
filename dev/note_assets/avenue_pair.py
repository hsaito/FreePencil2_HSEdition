"""v2.7 相当(精密)と v2.8 の手描き背景を、同じカメラで 1 枚ずつ撮る(どちらも STEP0 を押しただけ。設定は触らない)。

  blender -b --factory-startup --python avenue_pair.py -- [--pre out/avenue/avenue_pre.blend] [--out out/avenue/pair]
      [--res 1920] [--samples 16] [--cam-y -120] [--cam-z 16] [--lens 24]

出力: precise.png(v2.7 相当)/ background.png(v2.8 手描き背景の既定)/ 各 .blend
プレビューはどちらも「白」(線画を見せる)。
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
PRE = Path(arg("--pre", str(HERE / "out" / "avenue" / "avenue_pre.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "avenue" / "pair"))).resolve()
RES = int(arg("--res", "1920"))
SAMPLES = int(arg("--samples", "16"))
sys.path.insert(0, str(HERE.parent / "batch"))
sys.path.insert(0, str(HERE))
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
if "--no-farlod" in ARGV:          # 比較用: 遠い区画をまとめるを切る
    _vc = sys.modules[next(m for m in sys.modules if m.endswith(".vertex_color"))]
    _vc.far_lod_cameras = lambda scene: None
OUT.mkdir(parents=True, exist_ok=True)
STYLES = arg("--styles", "PRECISE,BACKGROUND").split(",")
for style, name in (("PRECISE", "precise"), ("BACKGROUND", "background")):
    if style not in STYLES:
        continue
    bpy.ops.wm.open_mainfile(filepath=str(PRE))
    sc = bpy.context.scene
    cam = sc.camera
    for k, axis in (("--cam-x", 0), ("--cam-y", 1), ("--cam-z", 2)):
        if arg(k) is not None:
            cam.location[axis] = float(arg(k))
    if arg("--lens"):
        cam.data.lens = float(arg("--lens"))
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.eevee.taa_render_samples = SAMPLES
    if arg("--bake-keys"):          # STEP0 の前にカメラの動きをキーにする(render_boulevard_move と同じ道)
        import cam_path
        cam.data.lens = float(arg("--lens", "28"))
        cam.data.shift_y = 0.0
        cam_path.bake(sc, cam, cam_path.parse(arg("--bake-keys")), int(arg("--frames", "288")))
        print("@@@ baked camera keys", sc.frame_start, sc.frame_end, flush=True)
    sc.fp_auto_style = style
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")       # STEP0 だけ。そのあと何も変えない
    print("@@@", style, {k: round(float(getattr(sc, k)), 3) for k in
                         ("fp_lw_far_amount", "fp_lw_relief", "fp_lw_strength", "fp_fine_lines")},
          "preview", sc.fp_preview_mode, "supersample", sc.fp_supersample, flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{name}.blend"))
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@ rendered", name, flush=True)
