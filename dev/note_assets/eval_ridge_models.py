"""実装した「広い塗り + 稜線の起伏」を、BlenderKit の実モデルで前後比較する。

比べるのは2条件だけ。どちらも STEP0 をそのまま通す。

  before  従来の推奨値 (併合 0.02% / 稜線の起伏なし)
  after   今回の推奨値 (併合 1.0%  / 稜線の起伏 0.25, 距離 0.08)

同じカメラ・同じライト・同じシードで撮り、線画を並べる。判定は画像で
行う(CLAUDE.md)。数値は補助として ink(黒画素率)だけ添える。

    blender -b --factory-startup --python eval_ridge_models.py -- \
        [--limit 12] [--res 900]
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "ridge_models"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "900"))
LIMIT = int(arg("--limit", "12"))
ONLY = arg("--only")          # "after" だけ撮ると作例並べに使える
MODELS_JSON = Path(arg("--models", str(HERE.parent / "batch" / "out" /
                                       "models.json")))
T0 = time.time()

CONDS = [
    ("before", {"fp_min_island_area_pct": 0.02, "fp_ridge_amount": 0.0}),
    ("after", {"fp_min_island_area_pct": 1.0, "fp_ridge_amount": 0.25,
               "fp_ridge_radius": 0.08}),
]


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def model_list():
    if MODELS_JSON.exists():
        data = json.loads(MODELS_JSON.read_text("utf-8"))
        rows = data["models"] if isinstance(data, dict) else data
        out = []
        for r in rows:
            p = Path(r["path"] if isinstance(r, dict) else r)
            name = r.get("name") if isinstance(r, dict) else p.stem
            if p.exists():
                out.append((name or p.stem, p))
        return out[:LIMIT]
    found = scan_models.find_blends(Path(scan_models.DEFAULT_ROOT),
                                   0.05 * 1e6, 150 * 1e6)
    return [(p.stem, p) for p in found[:LIMIT]]


def one(name, blend, cond, overrides):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    meshes, others = fp_batch.append_objects(blend)
    if not meshes:
        raise RuntimeError("メッシュ無し")
    # run_pipeline と同じ手順。リグの操作シェイプと外れジオメトリを
    # 隠してから枠に収める(これを飛ばすとフレーミングが壊れる)
    shape_names = set()
    for a in others:
        if a.type == "ARMATURE" and a.pose:
            for pb in a.pose.bones:
                if pb.custom_shape is not None:
                    shape_names.add(pb.custom_shape.name)
    for o in meshes:
        if (o.name in shape_names
                or o.name.lower().startswith(("cs_", "wgt", "shape_"))):
            o.hide_render = True
    content = [o for o in meshes if not o.hide_render] or meshes
    cluster = fp_batch.dominant_cluster(content)
    for o in content:
        if o not in cluster:
            o.hide_render = True
    framed = [o for o in content if o in cluster] or content
    fp_batch.normalize(meshes + others, framed)
    fp_batch.apply_white_material(meshes)
    fp_batch.setup_camera_and_light()

    sc.fp_use_random_seed = False
    sc.fp_color_seed = 42
    sc.fp_enable_compositor_view = False
    sc.fp_auto_detect_aov = False
    sc.fp_preview_mode = 'NONE'
    sc.fp_auto_supersample = False
    sc.fp_supersample = False
    # STEP0 のおすすめが上書きしないよう、比較する項目だけ手で持つ
    sc.fp_auto_merge = False

    sel = fp_batch.select_meshes()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    # STEP0 のあとに置く。STEP1 はもう走っているので塗り直す
    for k, v in overrides.items():
        setattr(sc, k, v)
    bpy.ops.object.select_all(action="DESELECT")
    for o in sel:
        o.select_set(True)
    bpy.context.view_layer.objects.active = sel[0]
    bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")

    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{name}_{cond}.png"
    fp_batch.render_still(sc, png, 1)
    m = fp_batch.lineart_metrics(png)
    return {"file": png.name, "ink": round(m.get("ink_ratio", 0.0), 5),
            "faces": sum(len(o.data.polygons) for o in meshes)}


def main():
    fp_batch.install_addon()
    rows = []
    conds = [c for c in CONDS if ONLY is None or c[0] == ONLY]
    for name, blend in model_list():
        shots = {}
        for cond, ov in conds:
            try:
                shots[cond] = one(name, blend, cond, ov)
            except Exception as e:                       # noqa: BLE001
                traceback.print_exc()
                say(f"{name} {cond}: 失敗 {e}")
        if len(shots) == len(conds):
            rows.append({"name": name, "shots": shots})
            k = conds[0][0]
            say(f"{name}: 面{shots[k]['faces']:,} "
                + " ".join(f"{c}={shots[c]['ink']:.4f}"
                            for c, _ in conds))
    (OUT / "index.json").write_text(
        json.dumps({"conds": [c for c, _ in conds], "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {len(rows)}体 {OUT}")


if __name__ == "__main__":
    main()
