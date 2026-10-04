"""町の形だけを簡易表示(Workbench)で撮る。線は出さない。

  blender -b --factory-startup --python check_town_views.py -- --blend <town_pre.blend> --out <dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
BLEND = Path(arg("--blend", str(HERE / "out" / "town_v4" / "town_pre.blend")))
OUT = Path(arg("--out", str(HERE / "out" / "town_v4" / "check")))
sys.argv = ["blender", "--"]
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
from mathutils import Vector      # noqa: E402
import shoot_town_v2 as st        # noqa: E402


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False
    cam = sc.camera
    st.FRAMES = 720
    for f in (60, 250, 330, 450, 600):
        st.aim(cam, f)
        sc.frame_set(f + 1)
        sc.render.filepath = str(OUT / f"cut_{f}.png")
        bpy.ops.render.render(write_still=True)

    def shot(name, pos, tgt, lens):
        cam.location = Vector(pos)
        cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(OUT / f"{name}.png")
        bpy.ops.render.render(write_still=True)
    shot("facade_close", (-2.0, 20.0, 6.0), (10.0, 34.0, 8.0), 28)
    shot("under_expressway", (0.0, 64.0, 1.7), (-20.0, 66.0, 9.0), 20)
    print("@@@ done", flush=True)


if __name__ == "__main__":
    main()
