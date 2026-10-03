"""並木道のカメラワークを、v2.7 相当(精密)と v2.8 手描き背景の両方で撮る(STEP0 済みの .blend を開くだけ)。

  blender -b --factory-startup --python render_boulevard_move.py -- --out out/boulevard/move_pv
      [--pair out/boulevard/pair] [--res 480] [--samples 4] [--frames 192] [--only 1,2,3]
出力: <out>/r0/fNNNN.png(精密)と <out>/r1/fNNNN.png(手描き背景)

カメラ: 地上 2.5m で前進 -> 途中から上昇して見下ろし、並木の海と奥のビル群を見渡す。
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
PAIR = Path(arg("--pair", str(HERE / "out" / "boulevard" / "pair"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "boulevard" / "move_pv"))).resolve()
RES = int(arg("--res", "480"))
SAMPLES = int(arg("--samples", "4"))
N = int(arg("--frames", "192"))
ONLY = {int(v) for v in arg("--only", "").split(",") if v}
STYLES = arg("--styles", "precise,background").split(",")
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * t * (t * (t * 6 - 15) + 10)


# カメラの要所(t, x, y, z, pitch, yaw)。間はエルミート曲線でなめらかにつなぐ(要所で止まらない)
KEYS = [tuple(float(v) for v in k.split(":")) for k in arg(
    "--keys", "0:-21.5:-60:2.5:91:0,0.35:-21.5:-8:2.5:97:-2,0.62:-11:32:14:95:-1,1:0:118:34:84:0").split(",")]


def _interp(t, col):
    ts = [k[0] for k in KEYS]
    vs = [k[col] for k in KEYS]
    if t <= ts[0]:
        return vs[0]
    if t >= ts[-1]:
        return vs[-1]
    j = max(i for i in range(len(ts) - 1) if ts[i] <= t)
    t0, t1 = ts[j], ts[j + 1]
    v0, v1 = vs[j], vs[j + 1]

    def slope(k):
        if k == 0:
            return (vs[1] - vs[0]) / (ts[1] - ts[0])
        if k == len(ts) - 1:
            return (vs[-1] - vs[-2]) / (ts[-1] - ts[-2])
        return (vs[k + 1] - vs[k - 1]) / (ts[k + 1] - ts[k - 1])

    h = t1 - t0
    u = (t - t0) / h
    m0, m1 = slope(j) * h, slope(j + 1) * h
    return ((2 * u ** 3 - 3 * u ** 2 + 1) * v0 + (u ** 3 - 2 * u ** 2 + u) * m0
            + (-2 * u ** 3 + 3 * u ** 2) * v1 + (u ** 3 - u ** 2) * m1)


def pose(i):
    """コマ番号 i(0 始まり)のカメラ位置と向き。"""
    t = i / max(1, N - 1)
    x, y, z, pitch, yaw = (_interp(t, c) for c in (1, 2, 3, 4, 5))
    return (x, y, z), (math.radians(pitch), 0.0, math.radians(yaw))


fp_batch.install_addon()
for style in STYLES:
    bpy.ops.wm.open_mainfile(filepath=str(PAIR / f"{style}.blend"))
    sc = bpy.context.scene
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.eevee.taa_render_samples = SAMPLES
    if arg("--preview"):                       # プレビューの種類(WHITE / MONO_LIGHT / NONE)
        sc.fp_preview_mode = arg("--preview")
    for kv in [v for v in arg("--set", "").split(",") if v]:   # 確かめ用: プロパティを変える(k=v)
        k, v = kv.split("=")
        setattr(sc, k, type(getattr(sc, k))(float(v)))
        print("@@@ set", k, getattr(sc, k), flush=True)
    cam = sc.camera
    # STEP0 の前にカメラの動きをキーにしてある(avenue_pair --bake-keys)と、キーが下の
    # 手書きの位置を上書きしてカメラが動かない。塗りは STEP0 で決まっているので消してよい
    cam.animation_data_clear()
    cam.data.lens = float(arg("--lens", "28"))
    cam.data.shift_y = 0.0
    movers = [o for o in sc.objects if "fp_v" in o]
    if arg("--plane"):                 # 飛行機の飛び方を撮影時に変える(塗りは位置に関係しないので STEP0 不要)
        y0, z0, x, v, vz = (float(v_) for v_ in arg("--plane").split(":"))
        for o in [o for o in movers if "fp_vz" in o][:1]:
            o["fp_y0"], o["fp_z0"], o["fp_v"], o["fp_vz"] = y0, z0, v, vz
            o.location.x = x
    d = OUT / ("r0" if style == "precise" else "r1")
    d.mkdir(parents=True, exist_ok=True)
    for i in range(N):
        if ONLY and (i + 1) not in ONLY:
            continue
        for o in movers:                       # 車・飛行機を動かす(STEP0 の塗りはメッシュ共有なので位置だけ変える)
            o.location.y = float(o["fp_y0"]) + float(o["fp_v"]) * i
            if "fp_vz" in o:
                o.location.z = float(o["fp_z0"]) + float(o["fp_vz"]) * i
        loc, rot = pose(i)
        cam.location = loc
        cam.rotation_euler = rot
        sc.render.filepath = str(d / f"f{i + 1:04d}.png")
        bpy.ops.render.render(write_still=True)
    print("@@@", style, "done", flush=True)
