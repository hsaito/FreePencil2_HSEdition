"""開発ビルドの通し番号を __init__.py に打つ / 外す。

  python scripts\\stamp_dev.py            # 今日の日付で採番して打つ
  python scripts\\stamp_dev.py --release  # 空にする(リリース版)
  python scripts\\stamp_dev.py --show     # いまの値を表示するだけ

番号は YYYYMMDD + 3桁の通し番号。同じ日に打ち直すと通し番号だけ増える。

なぜ要るか: バージョン番号を上げずに中身だけ差し替えると、画面の
「v2.6.2」が同じままで新旧の区別がつかない。実際、前日に起動したままの
Blender が古いコードを保持していたのに、表示が最新と同じで気づけなかった。
リリース時は --release で外すので、配布物には出ない。
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INIT = REPO / "__init__.py"
PAT = re.compile(r'^DEV_BUILD = "([^"]*)"$', re.M)


def current() -> str:
    m = PAT.search(INIT.read_text(encoding="utf-8"))
    if m is None:
        raise SystemExit(f"DEV_BUILD が {INIT.name} に見つからない")
    return m.group(1)


def next_number(now: dt.date) -> str:
    today = now.strftime("%Y%m%d")
    cur = current()
    if cur.startswith(today) and len(cur) == len(today) + 3:
        seq = int(cur[len(today):]) + 1
    else:
        seq = 1
    return f"{today}{seq:03d}"


def write(value: str) -> None:
    src = INIT.read_text(encoding="utf-8")
    INIT.write_text(PAT.sub(f'DEV_BUILD = "{value}"', src, count=1),
                    encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--release", action="store_true",
                   help="通し番号を外す(配布用)")
    p.add_argument("--show", action="store_true")
    p.add_argument("--set", default=None, help="任意の値を直接入れる")
    args = p.parse_args()

    if args.show:
        cur = current()
        print(f"[dev] {cur or '(リリース版・番号なし)'}")
        return
    if args.release:
        write("")
        print("[dev] リリース版にした(通し番号なし)")
        return
    value = args.set if args.set is not None else next_number(dt.date.today())
    write(value)
    print(f"[dev] {value}")


if __name__ == "__main__":
    main()
