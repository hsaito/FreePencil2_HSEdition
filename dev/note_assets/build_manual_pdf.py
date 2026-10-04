"""MANUAL_ja.md を配布用の PDF にする。

note で配る相手は Blender を使う絵描きなので、.md を渡すと Windows では
メモ帳が開いて `**太字**` や表のパイプがそのまま見える。読み物として
成立しないので PDF にする。

変換は Markdown -> HTML -> Chrome のヘッドレス印刷。Chrome を使うのは
日本語のフォント回りを自前で解決しなくて済むため(pandoc/LaTeX は CJK の
設定が要るし、この環境には入っていない)。

    python dev/note_assets/build_manual_pdf.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "MANUAL_ja.md"
import re as _re
_ver = _re.search(r'"version":\s*\((\d+),\s*(\d+),\s*(\d+)\)',
                  (ROOT / "__init__.py").read_text(encoding="utf-8"))
VERSION = ".".join(_ver.groups()) if _ver else "0.0.0"
OUT = ROOT / "dist" / f"FreePencil2_マニュアル_v{VERSION}.pdf"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

# 紙で読む前提の版面。本文 10.5pt / 行送り 1.75 は、A4 で1行が
# 40文字前後に収まる値。表は罫線を薄くして、数字を読む邪魔をしない
CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
body {
  font-family: "Yu Gothic", "Meiryo", "MS PGothic", sans-serif;
  font-size: 10.5pt; line-height: 1.75; color: #1a1a1a;
  -webkit-print-color-adjust: exact;
}
h1 {
  font-size: 20pt; margin: 0 0 4mm; padding-bottom: 3mm;
  border-bottom: 2px solid #1a1a1a;
}
h2 {
  font-size: 14pt; margin: 10mm 0 3mm; padding: 2mm 0 1.5mm;
  border-bottom: 1px solid #bbb; page-break-after: avoid;
}
h3 { font-size: 11.5pt; margin: 6mm 0 2mm; page-break-after: avoid; }
p, li { orphans: 2; widows: 2; }
ul, ol { padding-left: 6mm; }
li { margin: 1mm 0; }
strong { font-weight: 700; }
code {
  font-family: "Consolas", "MS Gothic", monospace; font-size: 9.5pt;
  background: #f0f0ee; padding: 0.4mm 1.2mm; border-radius: 1mm;
}
pre {
  background: #f6f6f4; border: 1px solid #ddd; border-radius: 1mm;
  padding: 3mm; overflow-x: auto; page-break-inside: avoid;
}
pre code { background: none; padding: 0; }
table {
  border-collapse: collapse; width: 100%; margin: 3mm 0;
  font-size: 9.5pt; page-break-inside: avoid;
}
th, td { border: 1px solid #ccc; padding: 1.6mm 2.5mm; text-align: left; }
th { background: #f0f0ee; font-weight: 700; }
hr { border: 0; border-top: 1px solid #ddd; margin: 8mm 0; }
a { color: #1a1a1a; }
figure {
  margin: 5mm 0; page-break-inside: avoid; text-align: center;
}
figure img {
  max-width: 100%; border: 1px solid #ddd; border-radius: 1mm;
}
/* サイドバーの切り出しは細長い。幅いっぱいに伸ばすと巨大になるうえ、
   独立した図として置くとページ下部に大きな空きが出る。実物と同じくらいの
   幅に留めて本文を回り込ませる */
figure:has(img[src*="02_step0"]), figure:has(img[src*="03_step3"]) {
  float: right; width: 62mm; margin: 1mm 0 4mm 6mm; text-align: left;
}
figure img[src*="02_step0"], figure img[src*="03_step3"] { max-width: 100%; }
/* 章が変わるところで回り込みを断ち切る。切らないと次の章の見出しが
   図の横に潜り込む */
h2 { clear: both; }
figcaption {
  font-size: 9pt; color: #555; margin-top: 1.5mm; text-align: left;
  line-height: 1.6;
}
"""

# 段落の途中で折り返された行を、空白を挟まずに繋ぐための判定。
# Markdown は改行を半角スペースにするので、そのままだと日本語の文の
# 途中に「同じ線画に なります」のような空白が入ってしまう
CJK_END = re.compile(
    "[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]$")
# 箇条書きの記号は直後に空白が要る。これを見ないと `**太字**` で始まる
# 段落を箇条書きと取り違えて、繋がずに空白を残してしまう
BLOCK = re.compile(r"^\s*(?:[-*+]\s|\d+\.\s|[>|#]|```|$)")
# 箇条書きの項目の続き(字下げした行)は、項目の行に繋いでよい。
# これを見ないと「設定を 消して」のように項目の中に空白が残った
LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s|\d+\.\s)")
# 行末の強調記号は文字と見なさない。`…ください。**` のような行も
# 日本語で終わっていると判定したい
TRAIL_EMPHASIS = re.compile(r"[*_`]+$")


def join_wrapped_lines(md: str) -> str:
    """日本語で折り返した行を、空白を入れずに繋ぐ。

    繋ぐのは「前の行が日本語の文字で終わり、前後どちらも箇条書きや表などの
    ブロック記法ではない」ときだけ。表や箇条書きの構造は壊さない。
    """
    lines = md.split("\n")
    if not lines:
        return md
    out = [lines[0]]
    for cur in lines[1:]:
        prev = out[-1]
        if (CJK_END.search(TRAIL_EMPHASIS.sub("", prev))
                and not BLOCK.match(cur)
                and (not BLOCK.match(prev)
                     or (LIST_ITEM.match(prev) and cur[:1].isspace()))):
            out[-1] = prev + cur.lstrip()
        else:
            out.append(cur)
    return "\n".join(out)


def chrome() -> str:
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("Chrome / Edge が見つからない")


def main() -> None:
    html_body = markdown.markdown(
        join_wrapped_lines(SRC.read_text(encoding="utf-8")),
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    # HTML は一時ディレクトリに置くので、図版の相対パスは解決できない。
    # リポジトリ内の実ファイルを指す file:// に書き換える
    def to_file_uri(m: re.Match) -> str:
        path = (ROOT / m.group(1)).resolve()
        if not path.exists():
            sys.exit(f"図版が無い: {path}")
        return f'src="{path.as_uri()}"'

    html_body = re.sub(r'src="((?!https?:|file:)[^"]+)"', to_file_uri,
                       html_body)

    page = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f"<style>{CSS}</style></head><body>{html_body}</body></html>")

    OUT.parent.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    src_html = tmp / "manual.html"
    src_html.write_text(page, encoding="utf-8")
    try:
        r = subprocess.run(
            [chrome(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={OUT}", "--virtual-time-budget=8000",
             src_html.as_uri()],
            capture_output=True, timeout=180)
        # Chrome は書き出しに成功しても非ゼロで終わることがあるので、
        # 終了コードではなく出来たファイルで判定する
        if not OUT.exists() or OUT.stat().st_size < 20_000:
            sys.exit(f"PDF が出来ていない (exit {r.returncode})\n"
                     + r.stderr.decode("utf-8", "replace")[-800:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{OUT}  {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
