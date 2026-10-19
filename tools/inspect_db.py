"""
Print the structure of a SQLite file: tables, columns, row counts, a few sample rows.
Opens the file read-only; never modifies it.

usage: python tools/inspect_db.py <path-to.db> [--rows N]
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def _short(v, n=40):
    s = repr(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--rows", type=int, default=3, help="sample rows per table (0 = none)")
    args = ap.parse_args()

    path = Path(args.db)
    if not path.is_file():
        print(f"ファイルが見つかりません: {path}", file=sys.stderr)
        return 1

    con = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    tables = [r[0] for r in con.execute(
        "select name from sqlite_master where type in ('table','view') and name not like 'sqlite_%' order by name")]
    print(f"# {path.name}  (テーブル/ビュー {len(tables)} 件)")
    for t in tables:
        q = '"' + t.replace('"', '""') + '"'
        cols = con.execute(f"pragma table_info({q})").fetchall()
        try:
            n = con.execute(f"select count(*) from {q}").fetchone()[0]
        except sqlite3.Error as e:
            n = f"取得不可({e})"
        print(f"\n## {t}  行数={n}")
        print("  列: " + ", ".join(f"{c[1]}({c[2] or '?'}{',PK' if c[5] else ''})" for c in cols))
        if args.rows > 0 and isinstance(n, int) and n:
            for row in con.execute(f"select * from {q} limit {args.rows}"):
                print("  例: " + " | ".join(_short(v) for v in row))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
