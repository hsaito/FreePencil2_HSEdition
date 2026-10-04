"""連番 2 種(r0 / r1)のちらつきを、2 階差分の平均で地図にする。

  python flicker_map.py --dir out/canyon2/move70 [--scale 2]

なめらかな動きでは 2 階差分(I[t-1] - 2 I[t] + I[t+1])は小さく、ちらつき(コマごとに
出たり消えたりする)では大きい。カメラが動くとエッジの位置が変わるぶんも出るが、OFF と ON は
同じ動きなので、差は「ちらつき」のぶん。白いほどちらつかない、黒いほどちらつく。
出力: flicker_map_r0.png / flicker_map_r1.png / flicker_compare.png / 数値(標準出力)
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
D = Path(arg("--dir", "out/canyon2/move70"))
SC = int(arg("--scale", "2"))          # 4K -> 1080p(再生で見る大きさ)へ縮める
TOP = float(arg("--gain", "4.0"))


def lum(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    g = bg.convert("L")
    if SC > 1:
        g = g.resize((g.size[0] // SC, g.size[1] // SC), Image.BOX)
    return np.asarray(g, np.float32)


names = sorted(p.name for p in (D / "r1").glob("f*.png"))
res = {}
for t in ("r0", "r1"):
    acc = None
    per_frame = []
    hot = []
    a = lum(D / t / names[0])
    b = lum(D / t / names[1])
    for k in range(2, len(names)):
        c = lum(D / t / names[k])
        d2 = np.abs(a - 2 * b + c)
        acc = d2 if acc is None else acc + d2
        per_frame.append(float(d2.mean()))
        hot.append(float((d2 > 40).mean()))
        a, b = b, c
    n = len(names) - 2
    res[t] = (acc / n, np.array(per_frame), np.array(hot))
    print(f"{t}: 2階差分の平均 {np.mean(res[t][1]):.3f} / 40 を超える画素の割合 {np.mean(res[t][2]) * 100:.3f}% "
          f"/ 最大のコマ {int(np.argmax(res[t][1])) + 2}")

font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 26)
h, w = res["r0"][0].shape
S = Image.new("RGB", (2 * w + 6, h + 40), "white")
d = ImageDraw.Draw(S)
for j, t in enumerate(("r0", "r1")):
    m = res[t][0]
    img = 255 - np.clip(m * TOP, 0, 255).astype(np.uint8)
    Image.fromarray(img).convert("RGB").save(D.parent / f"flicker_map_{t}.png")
    S.paste(Image.fromarray(img).convert("RGB"), (j * (w + 6), 40))
    d.text((j * (w + 6) + 8, 6), f"{'軽減 OFF' if t == 'r0' else '軽減 ON'}  ちらつき地図(黒いほどちらつく) 平均 {np.mean(res[t][1]):.3f}",
           fill="black", font=font)
S.save(D.parent / "flicker_compare.png")
print("saved", D.parent / "flicker_compare.png")
