"""eval_tree_clumps.py の絵を並べる。近は縮小、遠は木のまわりを等倍で切り出す。"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
OUT = Path(__file__).resolve().parent / "out" / "tree_clumps"
tags = ["current"] + [f"k{k}" for k in (sys.argv[1] if len(sys.argv) > 1 else "1,4,8,16,32").split(",")]
font = ImageFont.truetype(r"C:\Windows\Fonts\meiryo.ttc", 26)

def onwhite(p):
    im = Image.open(p).convert("RGBA"); a = np.asarray(im, dtype=np.float32) / 255
    rgb = a[..., :3] * a[..., 3:4] + (1 - a[..., 3:4]); return Image.fromarray((rgb * 255 + .5).astype(np.uint8))

names = sorted({p.name.split("_current_near")[0] for p in OUT.glob("*_current_near.png")})
for name in names:
    tw, th, pad, bar = 640, 360, 6, 40
    cols = len(tags)
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, 2 * (th + bar + pad) + pad), (120, 120, 120))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(tags):
        near = OUT / f"{name}_{t}_near.png"; far = OUT / f"{name}_{t}_far.png"
        if not near.exists():
            continue
        x = pad + i * (tw + pad)
        a = onwhite(near).resize((tw, th), Image.LANCZOS)          # 3840->640 (1/6)
        b = onwhite(far)                                            # 木は高さ 1/5 -> 1080p相当で切る
        W, H = b.size
        b = b.crop((W // 2 - tw, H // 2 - th, W // 2 + tw, H // 2 + th)).resize((tw, th), Image.LANCZOS)
        for row, im, lab in ((0, a, f"{t} 近(1/6)"), (1, b, f"{t} 遠(1080p等倍)")):
            y = pad + row * (th + bar + pad)
            d.rectangle([x, y, x + tw, y + bar], fill=(30, 30, 30)); d.text((x + 10, y + 6), lab, fill=(255, 255, 255), font=font)
            sheet.paste(im, (x, y + bar))
    sheet.save(OUT / f"sheet_{name}.png"); print(name)
