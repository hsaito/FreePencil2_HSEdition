"""町で、v2.7 相当(精密)と v2.8 の手描き背景を、同じコマ・同じカメラで撮る。

どちらも STEP0 を押しただけ(線の設定は触らない)。プレビューは町のデモと同じ
モノクロ(陰影の下限 0.55)にそろえる(線の下に敷く陰影の見せ方で、線の設定ではない)。

  blender -b --factory-startup --python town_pair.py -- --frames 250,450,700 [--res 960] [--samples 8]
      [--blend out/stripe_verify/town_stripe.blend] [--out out/town_pair] [--styles PRECISE,BACKGROUND]
出力: <out>/<style>_f0250.png ... と <out>/<style>.blend
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "stripe_verify" / "town_stripe.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "town_pair"))).resolve()
def _frames(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = (int(v) for v in part.split("-"))
            out += list(range(a, b + 1))
        elif part:
            out.append(int(part))
    return out


FRAMES = _frames(arg("--frames", "250,450,700"))
SEQ = arg("--seq")       # 連番として書く(<seq>/r0 = 精密, <seq>/r1 = 手描き背景, f0001.png から)
RES = int(arg("--res", "960"))
SAMPLES = int(arg("--samples", "8"))
STYLES = arg("--styles", "PRECISE,BACKGROUND").split(",")
REUSE = "--reuse" in ARGV          # 前回 STEP0 済みの <style>.blend を開いて撮るだけ
sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch               # noqa: E402
import shoot_town_v2 as st         # noqa: E402

fp_batch.install_addon()
if "--no-farlod" in ARGV:          # 比較用: 遠い区画をまとめるを切る
    _vc = sys.modules[next(m for m in sys.modules if m.endswith(".vertex_color"))]
    _vc.far_lod_cameras = lambda scene: None
OUT.mkdir(parents=True, exist_ok=True)
for style in STYLES:
    src = OUT / f"{style}.blend"
    if REUSE and src.exists():
        bpy.ops.wm.open_mainfile(filepath=str(src))
        sc = bpy.context.scene
    else:
        bpy.ops.wm.open_mainfile(filepath=str(BLEND))
        sc = bpy.context.scene
        meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        if "--bake-cam" in ARGV:            # カメラの動きをキーにする(ユーザーがキーで動かす場合と同じ)
            st.FRAMES = 720
            sc.frame_start, sc.frame_end = 1, 720
            for f in range(1, 721, 8):
                st.aim(sc.camera, f - 1)
                sc.camera.keyframe_insert("location", frame=f)
                sc.camera.keyframe_insert("rotation_euler", frame=f)
            sc.frame_set(1)
        sc.fp_auto_style = style
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")          # STEP0 だけ
        print("@@@", style, "STEP0", {k: round(float(getattr(sc, k)), 3) for k in
                                       ("fp_lw_far_amount", "fp_lw_relief", "fp_lw_strength", "fp_fine_lines")},
              flush=True)
        sc.fp_mono_floor = 0.55
        sc.fp_preview_mode = "MONO_LIGHT"
        bpy.ops.wm.save_as_mainfile(filepath=str(src))
    st.FRAMES = 720
    st.moving_cars(sc)
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.eevee.taa_render_samples = SAMPLES
    for k, f in enumerate(FRAMES, start=1):
        st.aim(sc.camera, f - 1)
        sc.frame_set(f)
        if SEQ:
            d = Path(SEQ) / ("r0" if style == "PRECISE" else "r1")
            d.mkdir(parents=True, exist_ok=True)
            sc.render.filepath = str(d / f"f{k:04d}.png")
        else:
            sc.render.filepath = str(OUT / f"{style}_f{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("@@@ rendered", style, f, flush=True)
print("@@@ done", flush=True)
