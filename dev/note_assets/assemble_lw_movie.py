"""「線の強弱(くぼみ)」のデモ動画を組み立てる。

eval_lw_movie.py が撮った 強弱なし/あり の連番を並べる。
中身はアドオンが組んだノードが出した絵で、Python での加工はしない
(白地に載せる・並べる・文字を置く、だけ)。

    0.0- 1.0s  タイトル
    1.0- 3.5s  強弱なしで半周。まずこれが今の FreePencil
    3.5- 4.5s  その場でワイプ。線が太る瞬間を見せる
    4.5- 9.5s  強弱ありで1周
    9.5-13.5s  左右分割で並べて1周
   13.5-16.0s  顔の拡大でクロスフェード
   16.0-17.0s  締め

  python dev/note_assets/assemble_lw_movie.py [--src out/lw_movie] [--fps 24]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
W, H = 1920, 1080
WHITE = (255, 255, 255)
INK = (24, 24, 28)
GREY = (150, 150, 158)


def _mod(name: str, path: str):
    s = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mx = _mod("mx", "eval_taper_mix.py")


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class Src:
    """連番を白地に載せて返す。読み直しが多いので少しだけ覚えておく。"""

    def __init__(self, root: Path):
        self.off = sorted((root / "off").glob("f*.png"))
        self.on = sorted((root / "on").glob("f*.png"))
        self.n = min(len(self.off), len(self.on))
        if self.n == 0:
            raise SystemExit(f"素材が無い: {root}")
        self._c = {}

    def get(self, kind: str, i: int) -> Image.Image:
        key = (kind, i % self.n)
        if key not in self._c:
            p = (self.off if kind == "off" else self.on)[i % self.n]
            im = Image.open(p).convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im).convert("RGB")
            if im.size != (W, H):
                im = im.resize((W, H), Image.LANCZOS)
            if len(self._c) > 24:
                self._c.pop(next(iter(self._c)))
            self._c[key] = im
        return self._c[key]


def caption(im: Image.Image, text: str, sub: str = "") -> Image.Image:
    d = ImageDraw.Draw(im)
    f = mx.font(46)
    d.text((70, H - 150), text, font=f, fill=INK)
    if sub:
        d.text((70, H - 90), sub, font=mx.font(30), fill=(90, 90, 98))
    return im


def title_card(lines, subs=()) -> Image.Image:
    im = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    y = H // 2 - 30 * len(lines) - 40
    for s in lines:
        f = mx.font(84)
        w = d.textbbox((0, 0), s, font=f)[2]
        d.text(((W - w) // 2, y), s, font=f, fill=INK)
        y += 108
    y += 20
    for s in subs:
        f = mx.font(36)
        w = d.textbbox((0, 0), s, font=f)[2]
        d.text(((W - w) // 2, y), s, font=f, fill=(110, 110, 118))
        y += 56
    return im


def wipe(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """左から右へ b が出てくる。境目に細い線を置いて位置を分からせる。"""
    x = int(W * t)
    im = a.copy()
    im.paste(b.crop((0, 0, x, H)), (0, 0))
    if 0 < x < W:
        ImageDraw.Draw(im).line([(x, 0), (x, H)], fill=(210, 90, 60), width=4)
    return im


def split(a: Image.Image, b: Image.Image) -> Image.Image:
    """左右に並べる。

    はじめは1枚を真ん中で切って左右に貼ったが、左右で見えている
    部位が違うので、比較ではなく1体の奇妙な頭に見えた。
    それぞれを正方形に切り出して丸ごと並べる。
    """
    im = Image.new("RGB", (W, H), WHITE)
    box = (W // 2 - H // 2, 0, W // 2 + H // 2, H)
    side = 880
    for i, src in enumerate((a, b)):
        tile = src.crop(box).resize((side, side), Image.LANCZOS)
        im.paste(tile, (W // 4 - side // 2 + i * (W // 2), (H - side) // 2 + 30))
    ImageDraw.Draw(im).line([(W // 2, 40), (W // 2, H - 40)],
                            fill=GREY, width=3)
    return im


def zoom(im: Image.Image, box) -> Image.Image:
    return im.crop(box).resize((W, H), Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "out" / "lw_movie"))
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    src = Path(a.src)
    S = Src(src)
    meta = json.loads((src / "movie.json").read_text(encoding="utf-8"))
    # キャプションの数字は同じ素材から測る(measure_lw_movie.py)。
    # 別の撮影の数字を書いたままにしない
    st = json.loads((src / "stats.json").read_text(encoding="utf-8"))
    black = f"真っ黒率 {st['off']['black_rate']:.1f}% → {st['on']['black_rate']:.1f}%"
    steady = (f"隣接フレーム差 {st['off']['step_mean']:.2f}%"
              f"→{st['on']['step_mean']:.2f}%")
    fps = a.fps
    tmp = src / "seq"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    frames = []

    def push(im):
        frames.append(im)

    # 1. タイトル
    for _ in range(fps):
        push(title_card(["線に強弱をつける"],
                        ["開いたところ(輪郭)は太く、くぼみに入るほど細く",
                         "線の出かたも自動で少し弱めに切り替わる",
                         "FreePencil2 v2.8 開発中"]))

    # 2. 強弱なしで、正面に戻ってくるように回す。
    # 頭から回すと、切り替えの瞬間が後頭部になって何も見えなかった
    span = S.n // 2
    n2 = int(fps * 2.5)
    for i in range(n2):
        k = S.n - span + int(i / n2 * span)
        push(caption(S.get("off", k).copy(), "強弱なし",
                     "いまの FreePencil。線はどこも同じ太さ"))

    # 3. 正面で止めてワイプ。太る瞬間だけを見せる
    hold = 0
    nw = int(fps * 1.0)
    for i in range(nw):
        t = (i + 1) / nw
        im = wipe(S.get("off", hold), S.get("on", hold), t)
        push(caption(im, "くぼみで強弱をつける",
                     "輪郭は太く、くぼみに入る線ほど細く"))

    # 4. 強弱ありで1周
    for i in range(int(fps * 5.0)):
        k = hold + int(i / (fps * 5.0) * S.n)
        push(caption(S.get("on", k).copy(), "強弱あり",
                     f"回してもちらつかない。{steady}"))

    # 5. 左右分割で1周
    for i in range(int(fps * 4.0)):
        k = int(i / (fps * 4.0) * S.n)
        im = split(S.get("off", k), S.get("on", k))
        d = ImageDraw.Draw(im)
        d.text((70, 60), "強弱なし", font=mx.font(44), fill=INK)
        d.text((W // 2 + 70, 60), "強弱あり", font=mx.font(44), fill=INK)
        push(im)

    # 6. 顔の拡大。クロスフェードで重ねると、太さの違う線が二重に見えて
    # 版ずれのようになった。ワイプで切り替える
    # 枠は 16:9 にそろえる。以前は 960x842 を 1920x1080 に伸ばしていて、
    # 顔が横に広がっていた(指摘あり)
    zh = H * 78 // 100
    zw = zh * W // H
    box = ((W - zw) // 2, H * 4 // 100, (W - zw) // 2 + zw, H * 4 // 100 + zh)
    za = zoom(S.get("off", 0), box)
    zb = zoom(S.get("on", 0), box)
    nz = int(fps * 3.0)
    for i in range(nz):
        t = min(1.0, max(0.0, (i / nz - 0.2) / 0.55))
        # 数字は同じ素材の実測(10フレームおき)
        push(caption(wipe(za, zb, t), black,
                     "線の芯が黒くなり、余分な線は減る"))

    # 7. 締め
    for _ in range(fps):
        push(title_card(["くぼみ(AO)で線に強弱"],
                        ["強弱ONで線の感度を1.2倍に自動で弱める",
                         "しきい値はカットに1回測って固定"]))

    for i, im in enumerate(frames):
        im.save(tmp / f"f{i:05d}.png")
    out = Path(a.out) if a.out else src / "line_weight_demo.mp4"
    cmd = [ffmpeg_exe(), "-y", "-framerate", str(fps),
           "-i", str(tmp / "f%05d.png"), "-c:v", "libx264", "-pix_fmt",
           "yuv420p", "-crf", "18", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"{len(frames)}フレーム / {len(frames) / fps:.1f}秒  "
          f"しきい値 {meta['edges']}  {black}  {steady}")
    print(out)


if __name__ == "__main__":
    main()
