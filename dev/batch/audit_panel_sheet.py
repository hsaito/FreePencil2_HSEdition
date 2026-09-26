"""audit_panel.py の結果を分類して、疑わしいものを並べた画像にする。

  python audit_panel_sheet.py out/audit/b452

分類(数値は目で見る前の仕分けにだけ使う。判定は並べた画像で行う):
  DEAD     変えても、やり直しても絵が変わらない
  REVERT   変えた直後は変わるが、STEP3 などのやり直しで元に戻る(v2.8.0 のプレビューと同じ型)
  NOTLIVE  その場で効くはずの項目(更新フックあり)なのに、やり直すまで変わらない
  OK       変わる
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

D = Path(sys.argv[1]).resolve()
REPO = Path(__file__).resolve().parents[2]
recs = json.loads((D / "props.json").read_text(encoding="utf-8"))
props_src = (REPO / "props.py").read_text(encoding="utf-8")
LIVE = set(re.findall(r'"(fp_\w+)":\s*\w+Property\((?:(?!\n        \),).)*?update=', props_src, re.S))
LIVE |= {f"fp_ch_{c}" for c in ("mecha", "depth", "bone", "gen", "mat")}


def load(name):
    im = Image.open(D / name).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return np.asarray(bg.convert("L"), dtype=np.float32)


def diff(a, b):
    x, y = load(a), load(b)
    if x.shape != y.shape:          # 2倍レンダの切り替えで大きさが変わる
        y = np.asarray(Image.fromarray(y).resize(x.shape[::-1]), dtype=np.float32)
    d = np.abs(x - y)
    return float((d > 24).mean() * 100)          # 目に見えて変わった画素の割合(%)


rows = []
for r in recs:
    if "error" in r or "skip" in r or "C" not in r:
        rows.append({**r, "cls": "ERROR" if "error" in r else "SKIP"})
        continue
    ab, bc, ac = diff(r["A"], r["B"]), diff(r["B"], r["C"]), diff(r["A"], r["C"])
    live = r["prop"] in LIVE
    th = 0.15
    if ac < th and ab < th:
        cls = "DEAD"
    elif ab >= th and ac < th:
        cls = "REVERT"
    elif live and ab < th and ac >= th:
        cls = "NOTLIVE"
    else:
        cls = "OK"
    rows.append({**r, "ab": ab, "bc": bc, "ac": ac, "live": live, "cls": cls})

(D / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
by = {}
for r in rows:
    by.setdefault(r["cls"], []).append(r)
for k in ("ERROR", "REVERT", "NOTLIVE", "DEAD", "SKIP", "OK"):
    for r in by.get(k, []):
        extra = (f"A-B {r['ab']:.2f}% B-C {r['bc']:.2f}% A-C {r['ac']:.2f}%" if "ab" in r
                 else (r.get("error", r.get("skip", ""))[-160:].replace("\n", " ")))
        print(f"{k:8s} {r['style']:10s} {r['prop']:28s} {r.get('from','')}->{r.get('to','')} "
              f"[{r.get('redo','')}] {extra}")

# 疑わしいもの(と比較のため OK からいくつか)を並べる
f = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 14)
sus = [r for r in rows if r["cls"] in ("REVERT", "NOTLIVE", "DEAD")]
W, H = 240, 180
if sus:
    s = Image.new("RGB", (330 + 3 * (W + 4), len(sus) * (H + 8)), "white")
    d = ImageDraw.Draw(s)
    for i, r in enumerate(sus):
        y = i * (H + 8)
        d.multiline_text((4, y + 6), f"{r['cls']}\n{r['style']}\n{r['prop']}\n{r['from']} -> {r['to']}\n"
                         f"やり直し: {r['redo']}\nA-B {r['ab']:.2f}%\nA-C {r['ac']:.2f}%",
                         fill="black", font=f)
        for c, key in enumerate(("A", "B", "C")):
            im = Image.open(D / r[key]).convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            s.paste(bg.convert("RGB").resize((W, H)), (330 + c * (W + 4), y))
    s.save(D / "suspects.png")
    print("sheet:", D / "suspects.png", len(sus))
