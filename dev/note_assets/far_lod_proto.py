"""試作: 遠い区画をまとめる(画面上の大きさでの併合)。アドオン本体は変えず、ここで差し込む。

STEP0 のカメラから見た、区画(島)ごとの画面上の面積 [内部レンダの px^2] を
  面積(ワールド) x (焦点距離px / 距離)^2 x |cos(視線と法線)|
で出し、しきい値より小さい区画を、隣の一番大きな区画へまとめる(小さい順)。
2 回の塗り(精密の線 fine_color と手描きの塗り)の両方に効く。

  blender -b --factory-startup --python far_lod_proto.py -- <pre.blend> <out_dir> --px 150 [--res 1920] [--style BACKGROUND]
出力: <out_dir>/lod<px>.png(白プレビュー)と lod<px>.blend
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
PRE, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
PX = float(arg("--px", "150"))
RES = int(arg("--res", "1920"))
STYLE = arg("--style", "BACKGROUND")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch          # noqa: E402
import numpy as np            # noqa: E402

fp_batch.install_addon()
mi = sys.modules[next(m for m in sys.modules if m.endswith(".mesh_islands"))]
MESH_OF = {}
STATS = {"objs": 0, "before": 0, "after": 0}
_init = mi.MeshTopology.__init__
_adj = mi.MeshTopology.island_adjacency


def init(self, mesh):
    _init(self, mesh)
    MESH_OF[id(self)] = mesh


def far_merge(topo, mesh):
    sc = bpy.context.scene
    users = [o for o in sc.objects if o.type == "MESH" and o.data == mesh and not o.hide_render]
    cam = sc.camera
    if not users or cam is None or len(topo.islands) <= 1:
        return
    nf = topo.n_faces
    nrm0 = np.empty(nf * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", nrm0)
    nrm0 = nrm0.reshape(nf, 3).astype(np.float64)
    cpos = np.array(cam.matrix_world.translation)
    pct = sc.render.resolution_percentage / 100.0
    fpx = sc.render.resolution_x * pct * cam.data.lens / cam.data.sensor_width
    proj = None
    # 同じメッシュを使う物(並木など)は、一番大きく写る個体に合わせる(手前の木を粗くしない)
    for obj in users:
        M = np.array(obj.matrix_world, dtype=np.float64)
        nrm = nrm0 @ np.linalg.inv(M[:3, :3])                 # 法線はワールドへ(逆転置)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        cw = topo.center.astype(np.float64) @ M[:3, :3].T + M[:3, 3]
        det = abs(np.linalg.det(M[:3, :3])) ** (2.0 / 3.0)
        area_w = topo.area.astype(np.float64) * det
        v = cw - cpos
        dist = np.maximum(np.linalg.norm(v, axis=1), 1e-3)
        cosv = np.abs((v / dist[:, None] * nrm).sum(1))
        p = area_w * (fpx / dist) ** 2 * np.maximum(cosv, 0.02)
        proj = p if proj is None else np.maximum(proj, p)
    area_w = topo.area.astype(np.float64)
    isl = topo.islands
    parea = np.array([proj[f].sum() for f in isl])
    warea = np.array([area_w[f].sum() for f in isl])
    nb = _adj(topo, boundary_only=False)
    # 窓や帯は壁に貼った別パーツで、辺では繋がらない。近い別パーツも隣とみなす
    mi.add_loose_part_proximity(topo, mesh, nb, max_islands=200000)
    parent = list(range(len(isl)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in sorted(range(len(isl)), key=lambda k: (parea[k], k)):
        ri = find(i)
        if parea[ri] >= PX:
            continue
        best, ba = -1, -1.0
        for j in nb[i]:
            rj = find(j)
            if rj != ri and warea[rj] > ba:
                best, ba = rj, warea[rj]
        if best < 0:
            continue
        parent[ri] = best
        parea[best] += parea[ri]
        warea[best] += warea[ri]
    merged = {}
    for i in range(len(isl)):
        if find(i) == i:
            merged[i] = [isl[i]]
    for i in range(len(isl)):
        r = find(i)
        if r != i:
            merged[r].append(isl[i])
    before = len(isl)
    topo.set_islands([np.concatenate(merged[k]) for k in sorted(merged)])
    STATS["objs"] += 1
    STATS["before"] += before
    STATS["after"] += len(topo.islands)


_clump = mi.clump_small_islands


def clump(topo, *a, **kw):
    # 葉を房にまとめる直前に差し込む(手描き背景では毎回通る)。呼ぶ側は戻り値が
    # 0 でなければ区画の一覧を読み直すので、まとめたときは 1 以上を返す
    n0 = len(topo.islands)
    if PX > 0 and id(topo) in MESH_OF:
        far_merge(topo, MESH_OF.pop(id(topo)))
    n = _clump(topo, *a, **kw)
    return n or (1 if len(topo.islands) != n0 else 0)


mi.MeshTopology.__init__ = init
mi.clump_small_islands = clump

OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(PRE))
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
sc.eevee.taa_render_samples = 16
sc.fp_auto_style = STYLE
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
print(f"@@@ px {PX}: 島 {STATS['before']} -> {STATS['after']}(のべ {STATS['objs']} 回)", flush=True)
sc.fp_preview_mode = "WHITE"
bpy.ops.freepencil2.link_button()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"lod{int(PX)}.blend"))
sc.render.filepath = str(OUT / f"lod{int(PX)}.png")
bpy.ops.render.render(write_still=True)
print("@@@ rendered", flush=True)
