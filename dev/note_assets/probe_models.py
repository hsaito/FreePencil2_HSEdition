"""デモに使う候補モデルを1枚ずつ試し撮りする。

これまでのデモは戦車・帆船・メカ・機関車を使い回していた。新しい版の
宣伝に見飽きた絵を出しても仕方がないので、未使用のモデルから選び直す。
長い連番を撮ってから「駄目だった」となるのを避けるため、まず1枚だけ
撮って目で見る。

  blender -b --factory-startup --python probe_models.py -- \
      --out <dir> [--res 1280]
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
OUT = Path(arg("--out", str(HERE / "out" / "probe"))).resolve()
RES_W = int(arg("--res", "1280"))
SS = 2

sys.argv = ["blender", "--", "--out", str(OUT), "--res", str(RES_W),
            "--ss", str(SS)]
sys.path.insert(0, str(HERE))
import make_demo_movie as dm      # noqa: E402
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

dm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)
RES_H = RES_W * 9 // 16
T0 = time.time()

# 過去のデモで使っていないもの。線画で映えそうな順に並べた。
# 商標のはっきりした車と航空機は、これまでの方針どおり外す
CANDIDATES = [
    ("anime_girl", "anime-girl*"),
    ("loli", "loli_anime_girl*"),
    ("man", "man_2*"),
    ("man01", "man_01*"),
    ("woman01", "woman_01*"),
    ("stylized_m", "stylized-male-ch*"),
    ("fredy", "fredy*"),
    ("mozo", "mozo*"),
    ("terna", "terna*"),
    ("cartoon_wag", "80-s-cartoon-wag*"),
]


def say(m: str) -> None:
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def one(tag: str, pattern: str) -> dict | None:
    blend = dm.find_blend(pattern)
    if blend is None:
        say(f"{tag}: 見つからない ({pattern})")
        return None
    try:
        meshes, _ = dm.load(blend)
    except Exception as exc:                            # noqa: BLE001
        say(f"{tag}: 読み込み失敗 {exc}")
        return None
    dm.grey(meshes)
    piv = dm.stage(meshes)
    sec = dm.setup_lines(meshes)
    nf = sum(len(o.data.polygons) for o in meshes if not o.hide_render)

    sc = bpy.context.scene
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 24
    sc.render.resolution_percentage = 100
    sc.render.resolution_x = RES_W * SS
    sc.render.resolution_y = RES_H * SS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.use_nodes = True
    fp_batch.render_still(sc, OUT / f"{tag}.png", SS)
    say(f"{tag}: 面{nf:,} STEP0 {sec:.1f}秒")
    return {"tag": tag, "faces": nf, "step0": round(sec, 1)}


def main() -> None:
    fp_batch.install_addon()
    rows = [r for r in (one(t, p) for t, p in CANDIDATES) if r]
    (OUT / "probe.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"完了 {len(rows)} 件 {OUT}")


if __name__ == "__main__":
    main()
