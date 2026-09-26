"""note に貼るための HTML を組む。

note の編集画面は、ブラウザでレンダリングした文章をそのまま貼り付けると
見出し・太字・箇条書きを保ったまま入る。画像だけは note 側へ改めて
アップロードする必要があるので、本文中の画像位置は「ここに何を貼るか」が
一目で分かる帯にしておく。

    <venv>/python dev/note_assets/build_article_html.py

出力は note/v27_article/貼り付け用.html。同じフォルダの img/ を参照する
ので、フォルダごと移動しても崩れない。
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
import sys as _sys
# 記事のフォルダ(既定は v2.7)。  --dir note/v28_article
DIR = (ROOT / _sys.argv[_sys.argv.index("--dir") + 1] if "--dir" in _sys.argv
       else ROOT / "note" / "v27_article")
SRC = DIR / "本文.md"
OUT = DIR / "貼り付け用.html"

# 有料ラインの位置。この見出しから下が有料
PAYWALL = "この記事について"

CSS = """
:root { color-scheme: light; }
body {
  margin: 0; background: #ececeb;
  font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", "Meiryo", sans-serif;
  color: #1a1a1a;
}
main {
  max-width: 660px; margin: 0 auto; padding: 48px 20px 120px;
  background: #fff; min-height: 100vh;
}
h1 { font-size: 30px; line-height: 1.45; margin: 0 0 28px; }
h2 {
  font-size: 22px; line-height: 1.5; margin: 52px 0 16px;
  padding-top: 20px; border-top: 1px solid #e6e6e6;
}
h3 { font-size: 18px; margin: 32px 0 12px; }
p, li { font-size: 16px; line-height: 1.9; }
ul { padding-left: 22px; }
li { margin: 6px 0; }
strong { font-weight: 700; }
blockquote {
  margin: 20px 0; padding: 12px 18px; border-left: 4px solid #d8d8d8;
  color: #444; background: #fafafa;
}
hr { border: 0; border-top: 1px solid #e6e6e6; margin: 40px 0; }
a { color: #1a6fb5; }

/* 画像・表のスロット。note では画像を手で入れ直すので、
   何をどこに入れるのかが分かる形にしておく */
figure.slot { margin: 28px 0; }
figure.slot .tag {
  display: flex; gap: 10px; align-items: center;
  background: #1f6feb; color: #fff; font-size: 13px; font-weight: 700;
  padding: 8px 12px; border-radius: 6px 6px 0 0; letter-spacing: .02em;
}
figure.slot.table .tag { background: #7a3fb5; }
figure.slot .tag .file {
  font-family: ui-monospace, Consolas, monospace; font-weight: 400;
  opacity: .92;
}
figure.slot img {
  display: block; width: 100%; border: 1px solid #e0e0e0; border-top: 0;
}
figure.slot figcaption {
  font-size: 13px; color: #666; line-height: 1.7; padding: 8px 2px 0;
}
.paywall {
  margin: 56px 0; padding: 14px 16px; border: 2px dashed #d94f4f;
  border-radius: 8px; color: #b03030; font-weight: 700; font-size: 15px;
  background: #fff6f6;
}
.howto {
  margin: 0 0 40px; padding: 16px 18px; background: #f5f7fa;
  border: 1px solid #dfe4ea; border-radius: 8px;
  font-size: 14px; line-height: 1.8; color: #333;
}
.howto b { color: #1a1a1a; }
.copybar {
  position: sticky; top: 0; z-index: 5; display: flex; gap: 10px;
  align-items: center; margin: 0 -20px 24px; padding: 10px 20px;
  background: #fff; border-bottom: 1px solid #e6e6e6;
}
.copybar button {
  font: inherit; font-size: 14px; font-weight: 700; cursor: pointer;
  padding: 8px 14px; border-radius: 6px; border: 1px solid #1f6feb;
  background: #1f6feb; color: #fff;
}
.copybar button.sub { background: #fff; color: #1f6feb; }
.copybar button:focus-visible { outline: 3px solid #9cc3ff; outline-offset: 2px; }
.copybar .msg { font-size: 13px; color: #1b7f3b; }
.part { position: relative; }
.titlebox {
  margin: 0 0 28px; padding: 12px 14px; border: 1px solid #dfe4ea;
  border-radius: 8px; background: #fafbfc;
}
.titlebox .lbl { font-size: 12px; color: #666; margin-bottom: 4px; }
.titlebox .t { font-size: 18px; font-weight: 700; line-height: 1.5; }
@media print { body { background: #fff; } main { max-width: none; } .copybar { display: none; } }
"""

# コピーするときは、画像の帯を「［画像N をここに：ファイル名］」の1行に置き換える。
# note には画像を貼れないので、アップロードする位置の目印だけ残す
COPY_JS = """
<script>
function fpClean(el){
  const c = el.cloneNode(true);
  c.querySelectorAll('figure.slot').forEach(f => {
    const tag = f.querySelector('.tag span');
    const file = f.querySelector('.file');
    const cap = f.querySelector('figcaption');
    const p = document.createElement('p');
    p.textContent = '［' + (tag ? tag.textContent.replace('▼ ', '').replace(' をここに挿入', '') : '画像')
      + ' をここに：' + (file ? file.textContent.replace('img/', '') : '') + '］'
      + (cap ? '　キャプション：' + cap.textContent : '');
    f.replaceWith(p);
  });
  c.querySelectorAll('.paywall').forEach(e => e.remove());
  return c;
}
function fpCopy(id, btn){
  const src = document.getElementById(id);
  const c = fpClean(src);
  const box = document.createElement('div');
  box.style.cssText = 'position:fixed;left:-99999px;top:0;';
  box.appendChild(c);
  document.body.appendChild(box);
  const r = document.createRange(); r.selectNodeContents(c);
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  sel.removeAllRanges(); box.remove();
  const msg = document.getElementById('fp-msg');
  const name = btn.textContent.replace(/\s*をコピー$/, '');
  msg.textContent = ok ? name + ' をコピーしました。note の編集画面に貼ってください'
                       : 'コピーできませんでした。本文を選択して Ctrl+C でコピーしてください';
}
</script>
"""

HOWTO = """<div class="howto">
<b>使い方</b> — 上のボタンで「タイトル」「無料部分」「有料部分」をコピーし、
note の編集画面に貼ってください（見出し・太字・箇条書きが残ります）。
<b>青い帯は画像の置き場所</b>です。貼った本文では「［画像N をここに：ファイル名］」の
1行になっているので、そこへ <b>img/</b> の同じファイルをアップロードし、
キャプションを入れてから、その1行を消してください。
赤い破線の位置が有料ラインです。
</div>"""


def slot(kind: str, num: str, fname: str, caption: str) -> str:
    """画像/表の置き場所を1つ組み立てる。"""
    cls = "slot table" if kind == "表" else "slot"
    label = f"{kind}{num}"
    return (
        f'<figure class="{cls}">'
        f'<div class="tag"><span>▼ {html.escape(label)} をここに挿入</span>'
        f'<span class="file">img/{html.escape(fname)}</span></div>'
        f'<img src="img/{html.escape(fname)}" alt="{html.escape(caption)}">'
        f'<figcaption>{html.escape(caption)}</figcaption></figure>')


MARKER = re.compile(
    r"<p>【(画像|表)(\d+)】\s*([0-9A-Za-z_.\-]+)\s*<br\s*/?>\s*"
    r"キャプション：(.*?)</p>", re.S)


def main() -> None:
    src = SRC.read_text(encoding="utf-8")
    global TITLE
    TITLE = next((ln[2:].strip() for ln in src.splitlines() if ln.startswith("# ")), "note")
    body = markdown.markdown(
        src,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )

    missing = []

    def repl(m: re.Match) -> str:
        kind, num, fname, cap = m.groups()
        if not (DIR / "img" / fname).exists():
            missing.append(fname)
        cap = re.sub(r"<[^>]+>", "", cap).strip()
        return slot(kind, num, fname, cap)

    body, n = MARKER.subn(repl, body)
    if missing:
        raise SystemExit("画像が無い: " + ", ".join(missing))

    # タイトルは note では別の欄に入れるので、本文から外して上に出す
    body = re.sub(r"^<h1>.*?</h1>\s*", "", body, count=1, flags=re.S)
    # 有料ラインで無料/有料の2つに分け、それぞれコピーできるようにする
    pay = f"<h2>{PAYWALL}</h2>"
    if pay in body:
        free, paid = body.split(pay, 1)
        paid = pay + paid
        body = (f'<div class="part" id="free">{free}</div>'
                '<div class="paywall">──── ここから有料 ────</div>'
                f'<div class="part" id="paid">{paid}</div>')
        buttons = ("<button onclick=\"fpCopy('free', this)\">無料部分をコピー</button>"
                   "<button onclick=\"fpCopy('paid', this)\">有料部分をコピー</button>")
    else:
        body = f'<div class="part" id="free">{body}</div>'
        buttons = "<button onclick=\"fpCopy('free', this)\">本文をコピー</button>"
    bar = ('<div class="copybar">'
           "<button class=\"sub\" onclick=\"fpCopy('title', this)\">タイトルをコピー</button>"
           f'{buttons}<span class="msg" id="fp-msg" role="status" aria-live="polite"></span></div>')
    titlebox = (f'<div class="titlebox"><div class="lbl">タイトル（note のタイトル欄へ）</div>'
                f'<div class="t" id="title">{html.escape(TITLE)}</div></div>')

    OUT.write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(TITLE)}（note 貼り付け用）</title>"
        f"<style>{CSS}</style>{COPY_JS}</head><body><main>{bar}{HOWTO}{titlebox}{body}</main>"
        "</body></html>", encoding="utf-8")
    print(f"{OUT}  スロット {n} 個  {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
