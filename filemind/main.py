#!/usr/bin/env python3
"""FileMind V1 命令行入口.

用法:
  python -m filemind.main init   --db D:\\filemind\\data.sqlite --dirs D:\\工作资料,D:\\项目
  python -m filemind.main scan   --db D:\\filemind\\data.sqlite
  python -m filemind.main serve  --db D:\\filemind\\data.sqlite [--port 8901]
  python -m filemind.main gui    --db D:\\filemind\\data.sqlite [--port 8901]  (桌面原生窗口版)

Windows 10 免管理员: pip install --user -r requirements.txt
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cfg_path(db_path: str) -> str:
    return os.path.splitext(db_path)[0] + ".config.json"


def cmd_init(args):
    from filemind import db as dbmod
    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    cfg = {"dirs": [d for d in args.dirs.split(",") if d.strip()]}
    json.dump(cfg, open(_cfg_path(args.db), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    con = dbmod.connect(args.db)
    ok = dbmod.check_fts5_trigram(con)
    con.close()
    print(f"初始化完成: {args.db}")
    print(f"监控目录: {cfg['dirs']}")
    print(f"SQLite FTS5+trigram: {'可用' if ok else '不可用!!请更换 Python'}")
    if not ok:
        sys.exit(2)


def cmd_scan(args):
    from filemind import chains as chainsmod
    from filemind import scan as scanmod
    cfg = json.load(open(_cfg_path(args.db), encoding="utf-8"))
    r = scanmod.scan(cfg["dirs"], args.db,
                     progress=lambda p, s: print(f"  [{s}] {p}"))
    c = chainsmod.build_chains(args.db)
    print(f"扫描完成: 新增 {r['added']}, 更新 {r['updated']}, 失踪 {r['missing']}; "
          f"版本链 {c['chains']} 条(其中 {c['need_review']} 条需人工确认)")


def cmd_serve(args):
    from filemind import app as appmod
    appmod.run(args.db, _cfg_path(args.db), port=args.port)


def cmd_gui(args):
    from filemind.gui import main_window as guimod
    guimod.main(db_path=args.db)


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", required=True, help="SQLite 数据库路径")
    ap = argparse.ArgumentParser(prog="filemind")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", parents=[common])
    p_init.add_argument("--dirs", required=True, help="逗号分隔的监控目录")
    sub.add_parser("scan", parents=[common])
    p_serve = sub.add_parser("serve", parents=[common])
    p_serve.add_argument("--port", type=int, default=8901)
    p_gui = sub.add_parser("gui", help="桌面原生窗口版(pywebview)")
    p_gui.add_argument("--db", default="", help="SQLite 数据库路径(默认 data/filemind.sqlite)")
    p_gui.add_argument("--port", type=int, default=8901)
    args = ap.parse_args()
    {"init": cmd_init, "scan": cmd_scan, "serve": cmd_serve, "gui": cmd_gui}[args.cmd](args)


if __name__ == "__main__":
    main()
