"""デモのカメラの通り道(要所をエルミート曲線でつなぐ)。render_boulevard_move.py と同じ式。

STEP0 の前にカメラの動きをキーにするとき(遠い区画をまとめるがカメラの近づく先を測る)に使う。
"""
import math


def parse(keys: str):
    return [tuple(float(v) for v in k.split(":")) for k in keys.split(",")]


def _interp(keys, t, col):
    ts = [k[0] for k in keys]
    vs = [k[col] for k in keys]
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


def pose(keys, i, n):
    """コマ番号 i(0 始まり、全 n コマ)のカメラ位置と向き。"""
    t = i / max(1, n - 1)
    x, y, z, pitch, yaw = (_interp(keys, t, c) for c in (1, 2, 3, 4, 5))
    return (x, y, z), (math.radians(pitch), 0.0, math.radians(yaw))


def bake(scene, cam, keys, n, step=8):
    """カメラの動きをキーにする(ユーザーがキーで動かした場合と同じ状態にする)。"""
    scene.frame_start, scene.frame_end = 1, n
    for i in list(range(0, n, step)) + [n - 1]:
        loc, rot = pose(keys, i, n)
        cam.location = loc
        cam.rotation_euler = rot
        cam.keyframe_insert("location", frame=i + 1)
        cam.keyframe_insert("rotation_euler", frame=i + 1)
    scene.frame_set(1)
