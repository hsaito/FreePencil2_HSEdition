"""見え方の監査(外側)。版ごとに visual_audit.py を回し、基準の絵と並べたシートを作る。

  python dev/batch/visual_audit_run.py                 4.5 と 5.2 で撮って、基準と並べる
  python dev/batch/visual_audit_run.py --set-baseline  今回の絵を基準にする(目で見て OK のときだけ)
      [--versions 4.5.2,5.2.0] [--tag now]

出力: dev/batch/out/visual_audit/<tag>/<版>/*.png と sheet_<版>.png
      基準は dev/batch/visual_audit_baseline/<版>/(git に入れる。目で見て OK の絵だけ)
シートは差の大きい順に「基準 | 今回 | 違う所(赤)」。差の数値は並べる順に使うだけ。
判定は絵で行う(CLAUDE.md)。基準の無い場面は今回の絵だけを並べる。
同じ版の中の決まりごと(例: プレビューを一巡させたら最初の白と同じ)も、絵で並べて出す。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
ROOT = HERE / "out" / "visual_audit"
TAG = arg("--tag", "now")
VERSIONS = arg("--versions", "4.5.2,5.2.0").split(",")
FONT = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 18)


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def diff(a, b):
    if a.size != b.size:
        b = b.resize(a.size)
    ga = np.asarray(a.convert("L"), np.float32)
    gb = np.asarray(b.convert("L"), np.float32)
    m = np.abs(ga - gb) > 24
    hl = np.asarray(b, np.float32) * 0.35 + 255 * 0.65
    hl[m] = (230, 0, 0)
    return float(m.mean() * 100), Image.fromarray(hl.astype(np.uint8))


def sheet(cur_dir: Path, base_dir: Path, out: Path):
    rows = []
    for p in sorted(cur_dir.glob("*.png")):
        cur = white(p)
        b = base_dir / p.name
        if b.exists():
            base = white(b)
            d, hl = diff(base, cur)
            rows.append((d, p.stem, [(base, "基準"), (cur, "今回"), (hl, f"違う所 {d:.2f}%")]))
        else:
            rows.append((-1.0, p.stem, [(cur, "今回(基準なし)")]))
    # 同じ版の中の決まりごと: プレビューを一巡させたら最初の白と同じ
    a, z = cur_dir / "preview_0_white.png", cur_dir / "preview_3_white.png"
    if a.exists() and z.exists():
        d, hl = diff(white(a), white(z))
        rows.append((d + 1000 if d > 0.5 else d, "プレビュー一巡(最初の白 vs 最後の白)",
                     [(white(a), "最初の白"), (white(z), "白→モノクロ→マテリアル→白"), (hl, f"違う所 {d:.2f}%")]))
    rows.sort(key=lambda r: -r[0])
    cw, ch = 480, 270
    S = Image.new("RGB", (3 * (cw + 6), len(rows) * (ch + 28)), "white")
    dr = ImageDraw.Draw(S)
    for i, (d, name, cells) in enumerate(rows):
        y = i * (ch + 28)
        for j, (im, lab) in enumerate(cells):
            S.paste(im.resize((cw, ch), Image.LANCZOS), (j * (cw + 6), y + 26))
            dr.text((j * (cw + 6) + 4, y + 3), f"{name}  {lab}", fill="black", font=FONT)
    S.save(out)
    for d, name, _ in rows:
        print(f"  {d:8.2f}  {name}")
    print("sheet:", out)


def main():
    for v in VERSIONS:
        exe = Path(f"C:/blender/blender-{v}-windows-x64/blender.exe")
        if not exe.exists():
            print("skip", v)
            continue
        out = ROOT / TAG / v
        if out.exists():
            shutil.rmtree(out)
        print("==", v)
        r = subprocess.run([str(exe), "-b", "--factory-startup", "--python", str(HERE / "visual_audit.py"),
                            "--", "--out", str(out)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=3600)
        if "@@@ done" not in r.stdout:
            print(r.stdout[-3000:])
            print(r.stderr[-2000:])
            raise SystemExit(f"{v}: 監査が最後まで回らなかった")
        base = HERE / "visual_audit_baseline" / v
        if "--set-baseline" in ARGV:
            if base.exists():
                shutil.rmtree(base)
            shutil.copytree(out, base)
            print("基準にした:", base)
        sheet(out, base, ROOT / TAG / f"sheet_{v}.png")


main()
