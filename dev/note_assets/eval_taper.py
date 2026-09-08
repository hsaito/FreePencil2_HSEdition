"""入り抜き(線の端を細くする)の実験。素材を撮るところまで。

仮説: 尖っている頂点をマスクにして、そこの線を消せば入り抜きになる。

アドオン本体には触らない。線のパスと、尖り具合のマスクを別々に描いて
出すだけ。合成は eval_taper_mix.py が画像の上で行う。効くと分かって
から、初めてノードに入れる。

尖り具合の測り方:
    p = dot(normalize(P_v - mean(P_neighbours)), N_v) / 平均辺長
  頂点が近傍の平均から法線の向きに飛び出していれば正(凸に尖っている)、
  へこんでいれば負、平らなら 0。辺長で割ってスケールに依存させない。

出すもの:
    line.png    いつもの線画 (白マテリアル・白地に黒線)
    plain.png   陰影のみ
    point.png   尖り具合を白黒で出したもの (正の側だけ)
    conc.png    へこみ側だけ (比較用)

  blender -b --factory-startup --python eval_taper.py -- \
      --out <dir> [--model suzanne|<pattern>] [--res 1400] [--subdiv 2]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "taper"))).resolve()
RES_W = int(arg("--res", "1400"))
SS = int(arg("--ss", "2"))
MODEL = arg("--model", "suzanne")
SUBDIV = int(arg("--subdiv", "2"))

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W),
            "--ss", str(SS)]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()
ATTR = "fp_pointy"


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def pointiness(mesh) -> np.ndarray:
    """頂点ごとの尖り具合を返す。凸が正、へこみが負、平らが 0。

    近傍の平均位置からのずれを法線に射影する。Cycles の Pointiness と
    同じ考え方だが、EEVEE では Pointiness が使えないので自分で出す。
    """
    nv = len(mesh.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)
    nrm = np.empty(nv * 3, dtype=np.float64)
    mesh.vertices.foreach_get("normal", nrm)
    nrm = nrm.reshape(nv, 3)

    ne = len(mesh.edges)
    ev = np.empty(ne * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(ne, 2)
    a, b = ev[:, 0], ev[:, 1]

    # 近傍の重心。辺の両端に相手の座標を足し込む
    acc = np.zeros((nv, 3), dtype=np.float64)
    cnt = np.zeros(nv, dtype=np.float64)
    np.add.at(acc, a, co[b])
    np.add.at(acc, b, co[a])
    np.add.at(cnt, a, 1.0)
    np.add.at(cnt, b, 1.0)
    lone = cnt == 0
    cnt[lone] = 1.0
    mean = acc / cnt[:, None]

    d = co - mean
    # 平均辺長で割る。モデルの大きさや密度で値が変わらないようにする
    elen = np.linalg.norm(co[a] - co[b], axis=1)
    scale = float(elen.mean()) if ne else 1.0
    p = (d * nrm).sum(axis=1) / max(scale, 1e-9)
    p[lone] = 0.0
    return p


def write_attr(obj, values: np.ndarray, positive: bool) -> None:
    """尖り具合を頂点カラーに書く。0..1 に丸めて白黒で入れる。"""
    me = obj.data
    v = values if positive else -values
    v = np.clip(v, 0.0, None)
    hi = float(np.percentile(v, 99.0)) if v.size else 1.0
    v = np.clip(v / max(hi, 1e-6), 0.0, 1.0)

    lay = me.color_attributes.get(ATTR)
    if lay is None:
        lay = me.color_attributes.new(name=ATTR, type="FLOAT_COLOR",
                                      domain="CORNER")
    nl = len(me.loops)
    vi = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("vertex_index", vi)
    c = np.empty((nl, 4), dtype=np.float32)
    c[:, 0] = c[:, 1] = c[:, 2] = v[vi]
    c[:, 3] = 1.0
    lay.data.foreach_set("color", c.ravel())
    me.update()


def attr_material():
    mat = bpy.data.materials.new("FP_Pointy")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = ATTR
    em = nt.nodes.new("ShaderNodeEmission")
    ou = nt.nodes.new("ShaderNodeOutputMaterial")
    ou.location = (240, 0)
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
    return mat


def build_suzanne():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    if SUBDIV > 0:
        m = o.modifiers.new("Subdivision", "SUBSURF")
        m.levels = m.render_levels = SUBDIV
        bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    return [o]


def main() -> None:
    fp_batch.install_addon()
    if MODEL == "suzanne":
        meshes = build_suzanne()
    else:
        blend = dm.find_blend(MODEL)
        if blend is None:
            raise SystemExit(f"見つからない: {MODEL}")
        meshes, _ = dm.load(blend)
    dm.grey(meshes)
    piv = dm.stage(meshes)

    sc = bpy.context.scene
    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    sc.fp_auto_white_preview = False
    sc.fp_white_preview = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_white_preview = True
    say(f"STEP0 {time.time() - t:.1f}秒")

    stats = []
    for o in meshes:
        p = pointiness(o.data)
        stats.append({"obj": o.name, "verts": len(o.data.vertices),
                      "p_min": round(float(p.min()), 4),
                      "p_max": round(float(p.max()), 4),
                      "p_p99": round(float(np.percentile(p, 99)), 4)})
        o["_fp_p"] = 1
    say(f"尖り具合を計算: {stats[:2]}")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W * SS
    sc.render.resolution_y = RES_H * SS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True

    sc.use_nodes = True
    fp_batch.render_still(sc, OUT / "line.png", SS)
    sc.use_nodes = False
    sc.fp_white_preview = False
    fp_batch.render_still(sc, OUT / "plain.png", SS)

    # マスクは合成を切って、素の発光で撮る。線画と画角が同じになる
    saved = {o.name: [s.material for s in o.material_slots] for o in meshes}
    pmat = attr_material()
    keep = sc.view_settings.view_transform
    sc.view_settings.view_transform = "Standard"
    for sign, name in ((True, "point.png"), (False, "conc.png")):
        for o in meshes:
            write_attr(o, pointiness(o.data), sign)
            for s in o.material_slots:
                s.material = pmat
        fp_batch.render_still(sc, OUT / name, SS)
    sc.view_settings.view_transform = keep
    for o in meshes:
        for s, m in zip(o.material_slots, saved[o.name]):
            s.material = m

    (OUT / "taper.json").write_text(json.dumps(
        {"model": MODEL, "subdiv": SUBDIV, "res": [RES_W, RES_H],
         "stats": stats}, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {OUT}")


if __name__ == "__main__":
    main()
