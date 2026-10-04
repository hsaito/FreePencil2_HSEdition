"""画面の一部を録画して連番 PNG にする。

ffmpeg がこの環境に無いので、mss で画面を掴んで1枚ずつ保存する。
あとで Blender に渡して mp4 にする。

マウスカーソルは画面キャプチャには含まれない (Windows の仕様)。
必要なら合成の側で描き足すこと。

    <venv>/python capture_screen.py --out <dir> --rect 2560,0,1920,1080 \
        --sec 60 --fps 24

start.json に開始時刻を書く。Blender 側のログの時刻と突き合わせて、
どのフレームがどの操作かを後から決められるようにする。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import mss
from PIL import Image


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rect", required=True, help="left,top,width,height")
    ap.add_argument("--sec", type=float, default=60.0)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()

    left, top, width, height = (int(v) for v in a.rect.split(","))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for old in list(out.glob("c*.png")) + list(out.glob("c*.jpg")):
        old.unlink()

    region = {"left": left, "top": top, "width": width, "height": height}
    step = 1.0 / a.fps
    t0 = time.time()
    (out / "start.json").write_text(
        json.dumps({"t0": t0, "fps": a.fps, "rect": region}), encoding="utf-8")

    n = 0
    stamps: list[float] = []
    with mss.mss() as sct:
        while True:
            due = t0 + n * step
            now = time.time()
            if now < due:
                time.sleep(due - now)
            if time.time() - t0 >= a.sec:
                break
            shot = sct.grab(region)
            im = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            if a.scale != 1.0:
                im = im.resize((round(im.width * a.scale),
                                round(im.height * a.scale)), Image.LANCZOS)
            # PNG だと保存が間に合わず、指定した fps の6割ほどしか撮れない。
            # JPEG なら追いつく。UI の文字も 92 なら読める
            im.save(out / f"c{n:05d}.jpg", quality=92, subsampling=0)
            stamps.append(round(time.time() - t0, 4))
            n += 1
    # 実際に撮れた時刻。取りこぼしがあるので、等間隔だと思ってはいけない
    (out / "times.json").write_text(json.dumps(stamps), encoding="utf-8")
    print(f"captured {n} frames -> {out}  実測 {n / max(stamps[-1], 1e-9):.1f} fps")


if __name__ == "__main__":
    main()
