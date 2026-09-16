"""遠景つぶれ軽減の案を合成して並べる(後段)。eval_far_ideas.py の後に回す。

撮った base/thin/sens/thin_sens と深度から、深度や局所密度を使う案を
作り、撮った案(relief*)と一緒に 4x4 のシートにする。

    fade        奥ほど白へ寄せる(空気遠近)
    blur        奥ほどぼかす(3段階、ぼかし半径 1.5/3/6px @200%)
    fade_blur   ぼかし + 白寄せ
    width       奥ほど強弱を細い線(強弱OFF)に差し替える
    width_sens  奥ほど「細い線 + 線を減らす」に差し替える
    sens_far    奥ほど「線を減らす(強弱のまま)」に差し替える
    erode       線が詰まっている所(局所密度)だけ線を1px削る
    open3/5     奥だけ「開き」(細い線を消して太い輪郭だけ残す)
    width_open3 奥を強弱OFFの線にしてから開き
    width_fade  width + 弱い白寄せ
    blur_width  width + 奥だけ弱いぼかし

出力:
    <out>/f####_<tag>.png           合成した案(2x のまま)
    <out>/sheet_f####_crop.png      一番詰まっている遠景を等倍で切り出した 4x4
    <out>/sheet_f####_1080p.png     同じ所を 1080p の見え方(半分に縮小)で
    <out>/sheet_f####_full.png      全体を縮めた 4x4
    <out>/metrics.json

  python eval_far_ideas_post.py [--out out/far_ideas] [--near 6 --far 90]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(HERE / "out" / "far_ideas"))
ap.add_argument("--near", type=float, default=6.0)
ap.add_argument("--far", type=float, default=90.0)
ap.add_argument("--crop", default="960x540")
A = ap.parse_args()
OUT = Path(A.out).resolve()
CW, CH = (int(v) for v in A.crop.split("x"))

ORDER = ["base", "relief05", "relief10", "relief10_wide",
         "relief03_tight", "sens", "thin", "thin_sens",
         "thin_sens3", "fade", "blur", "fade_blur",
         "width", "width_sens", "width_sens3", "sens_far",
         "erode", "width_fade", "blur_width", "open3",
         "open5", "width_open3", "width_sens3_fade", "width_sens3_open3"]
LABEL = {
    "base": "今のまま", "relief05": "つぶれ軽減 0.5", "relief10": "つぶれ軽減 1.0",
    "relief10_wide": "つぶれ軽減 1.0 半径12", "sens": "感度1.8(線を減らす)",
    "thin": "強弱OFF", "thin_sens": "強弱OFF+感度1.8", "fade": "奥を白へ(空気遠近)",
    "blur": "奥をぼかす", "fade_blur": "ぼかし+白へ", "width": "奥ほど細い線へ",
    "width_sens": "奥ほど細い線+線を減らす", "sens_far": "奥ほど線を減らす",
    "erode": "詰まった所だけ1px削る", "width_fade": "奥ほど細い線+弱い白",
    "blur_width": "奥ほど細い線+弱いぼかし",
    "relief03_tight": "つぶれ軽減 0.3 半径3 しきい0.5", "thin_sens3": "強弱OFF+感度3.0",
    "width_sens3": "奥ほど細い線+感度3.0", "open3": "奥の細い線を消す(開き3px)",
    "open5": "奥の細い線を消す(開き5px)", "width_open3": "奥ほど細い線→開き3px",
    "width_sens3_fade": "奥ほど細い線+感度3.0+弱い白",
    "width_sens3_open3": "奥ほど細い線+感度3.0→開き3px"}


def load_rgb(p: Path) -> np.ndarray:
    im = Image.open(p).convert("RGBA")
    a = np.asarray(im, dtype=np.float32) / 255.0
    rgb, al = a[..., :3], a[..., 3:4]
    return rgb * al + (1.0 - al)          # 白に載せる


def to_img(a: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def gauss(a: np.ndarray, r: float) -> np.ndarray:
    return np.asarray(to_img(a).filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255.0


def box_gray(g: np.ndarray, r: int) -> np.ndarray:
    im = Image.fromarray((np.clip(g, 0, 1) * 255 + 0.5).astype(np.uint8), "L")
    return np.asarray(im.filter(ImageFilter.BoxBlur(r)), dtype=np.float32) / 255.0


def lerp(a, b, w):
    w = w[..., None] if w.ndim == 2 else w
    return a * (1.0 - w) + b * w


def ramp(d, lo, hi):
    return np.clip((d - lo) / max(hi - lo, 1e-6), 0.0, 1.0)


def depth01(z: np.ndarray) -> np.ndarray:
    d = np.clip((z - A.near) / (A.far - A.near), 0.0, 1.0) ** 0.7
    d[z > 1e6] = 1.0
    return d.astype(np.float32)


def metrics(rgb: np.ndarray) -> dict:
    g = rgb.mean(axis=2)
    ink = g < 0.5
    solid = ink.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            solid &= np.roll(np.roll(ink, dy, 0), dx, 1)
    return {"ink": round(float(ink.mean()) * 100, 2),
            "crush": round(float(solid.mean()) * 100, 2)}


def find_crop(base: np.ndarray, d: np.ndarray):
    """深度 0.3 より奥で、インクが一番詰まっている所を切り出す"""
    ink = (base.mean(axis=2) < 0.5).astype(np.float32)
    small = np.asarray(Image.fromarray((ink * 255).astype(np.uint8), "L")
                       .resize((base.shape[1] // 8, base.shape[0] // 8), Image.BOX),
                       dtype=np.float32) / 255.0
    ds = np.asarray(Image.fromarray((d * 255).astype(np.uint8), "L")
                    .resize(small.shape[::-1], Image.BOX), dtype=np.float32) / 255.0
    score = box_gray(small * (ds > 0.3), CH // 24)
    y, x = np.unravel_index(int(score.argmax()), score.shape)
    cx, cy = x * 8, y * 8
    x0 = int(np.clip(cx - CW // 2, 0, base.shape[1] - CW))
    y0 = int(np.clip(cy - CH // 2, 0, base.shape[0] - CH))
    return x0, y0


def font(size):
    for p in (r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msgothic.ttc",
              r"C:\Windows\Fonts\YuGothM.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def sheet(tiles: list[tuple[str, Image.Image, str]], path: Path):
    tw, th = tiles[0][1].size
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    pad = 6
    bar = 40
    W = cols * (tw + pad) + pad
    H = rows * (th + bar + pad) + pad
    canvas = Image.new("RGB", (W, H), (120, 120, 120))
    dr = ImageDraw.Draw(canvas)
    f = font(26)
    for i, (tag, im, note) in enumerate(tiles):
        c, r = i % cols, i // cols
        x = pad + c * (tw + pad)
        y = pad + r * (th + bar + pad)
        dr.rectangle([x, y, x + tw, y + bar], fill=(30, 30, 30))
        dr.text((x + 10, y + 6), f"{LABEL.get(tag, tag)}   {note}", fill=(255, 255, 255), font=f)
        canvas.paste(im, (x, y + bar))
    canvas.save(path)


def main():
    frames = sorted({int(p.stem[1:5]) for p in OUT.glob("f????_base.png")})
    allm = {}
    for fr in frames:
        pre = OUT / f"f{fr:04d}_"
        base = load_rgb(Path(f"{pre}base.png"))
        thin = load_rgb(Path(f"{pre}thin.png"))
        sens = load_rgb(Path(f"{pre}sens.png"))
        thin_sens = load_rgb(Path(f"{pre}thin_sens.png"))
        z = np.load(f"{pre}depth.npy")
        assert z.shape == base.shape[:2], (z.shape, base.shape)
        d = depth01(z)
        far = ramp(d, 0.15, 0.7)             # 奥ほど 1

        v = {}
        v["fade"] = lerp(base, np.ones_like(base), 0.65 * d)
        b = base
        for r, lo in ((1.5, 0.15), (3.0, 0.4), (6.0, 0.7)):
            b = lerp(b, gauss(base, r), ramp(d, lo, lo + 0.25))
        v["blur"] = b
        v["fade_blur"] = lerp(b, np.ones_like(b), 0.5 * d)
        v["width"] = lerp(base, thin, far)
        v["width_sens"] = lerp(base, thin_sens, far)
        v["sens_far"] = lerp(base, sens, far)
        ink = 1.0 - base.mean(axis=2)
        dens = box_gray(ink, 12)
        w = ramp(dens, 0.30, 0.80)
        eroded = np.asarray(to_img(base).filter(ImageFilter.MaxFilter(3)), dtype=np.float32) / 255.0
        v["erode"] = lerp(base, eroded, w)
        v["width_fade"] = lerp(v["width"], np.ones_like(base), 0.35 * d)
        bw = v["width"]
        for r, lo in ((1.2, 0.35), (2.5, 0.65)):
            bw = lerp(bw, gauss(v["width"], r), ramp(d, lo, lo + 0.25))
        v["blur_width"] = bw
        thin_sens3 = load_rgb(Path(f"{pre}thin_sens3.png"))
        v["width_sens3"] = lerp(base, thin_sens3, far)

        def opening(img, k):
            o = to_img(img).filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))
            return np.asarray(o, dtype=np.float32) / 255.0
        v["open3"] = lerp(base, opening(base, 3), far)
        v["open5"] = lerp(base, opening(base, 5), far)
        v["width_open3"] = lerp(base, opening(thin, 3), far)
        v["width_sens3_fade"] = lerp(v["width_sens3"], np.ones_like(base), 0.35 * d)
        v["width_sens3_open3"] = lerp(base, opening(thin_sens3, 3), far)
        for tag, img in v.items():
            to_img(img).save(f"{pre}{tag}.png")

        x0, y0 = find_crop(base, d)
        m = {}
        crops, fulls, halfs = [], [], []
        hx0 = int(np.clip(x0 + CW // 2 - CW, 0, base.shape[1] - 2 * CW))
        hy0 = int(np.clip(y0 + CH // 2 - CH, 0, base.shape[0] - 2 * CH))
        for tag in ORDER:
            p = Path(f"{pre}{tag}.png")
            if not p.exists():
                continue
            rgb = load_rgb(p)
            crop = rgb[y0:y0 + CH, x0:x0 + CW]
            m[tag] = {"crop": metrics(crop), "full": metrics(rgb)}
            note = f"真っ黒 {m[tag]['crop']['crush']:.2f}%  インク {m[tag]['crop']['ink']:.1f}%"
            crops.append((tag, to_img(crop), note))
            fulls.append((tag, to_img(rgb).resize((CW, CH), Image.LANCZOS),
                          f"真っ黒 {m[tag]['full']['crush']:.2f}%"))
            halfs.append((tag, to_img(rgb[hy0:hy0 + 2 * CH, hx0:hx0 + 2 * CW])
                          .resize((CW, CH), Image.LANCZOS), "1080p の見え方"))
        sheet(crops, OUT / f"sheet_f{fr:04d}_crop.png")
        sheet(fulls, OUT / f"sheet_f{fr:04d}_full.png")
        sheet(halfs, OUT / f"sheet_f{fr:04d}_1080p.png")
        allm[fr] = {"crop": [x0, y0, CW, CH], "metrics": m}
        print(f"f{fr:04d} 切り出し ({x0},{y0})")
        for tag in ORDER:
            if tag in m:
                print(f"   {tag:<14} 切出 真っ黒{m[tag]['crop']['crush']:5.2f}% インク{m[tag]['crop']['ink']:5.1f}%"
                      f"   全体 真っ黒{m[tag]['full']['crush']:5.2f}%")
    (OUT / "metrics.json").write_text(json.dumps(allm, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
