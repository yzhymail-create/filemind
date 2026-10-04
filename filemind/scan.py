#!/usr/bin/env python3
"""增量巡检:用 (路径, 大小, 修改时间) 账本比对,只处理新增/变化/失踪文件.

- 未变文件直接跳过,几万文件也只要几秒.
- 新文件/变化文件:提文本 -> 算 sha256/simhash -> 写库 -> 更新 FTS.
- 失踪文件:标记 missing(宽限期),不立即删记录,供改名/移动续血缘判断.
"""
from __future__ import annotations

import hashlib
import os

from . import db as dbmod
from . import extract as extmod
from . import simhash as shmod

SUPPORTED_EXTS = {".txt", ".md", ".csv", ".log", ".ini", ".cfg",
                  ".docx", ".xlsx", ".pptx", ".pdf"}


def _sha256(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _index_text(con, file_id: int, text: str):
    con.execute("DELETE FROM fts_docs WHERE file_id=?", (file_id,))
    if text.strip():
        con.execute("INSERT INTO fts_docs(file_id, text) VALUES (?,?)", (file_id, text))


def scan(dirs: list, db_path: str, progress=None) -> dict:
    con = dbmod.connect(db_path)
    try:
        result = _scan_inner(con, dirs, progress)
        con.commit()
        return result
    except Exception as e:
        # 扫描中断或出错，回滚事务
        try:
            con.rollback()
        except Exception:
            pass
        raise e
    finally:
        con.close()


def _scan_inner(con, dirs, progress) -> dict:
    t0 = dbmod.now()
    # 检查是否有未完成的扫描记录
    unfinished = con.execute("SELECT id FROM scan_log WHERE finished_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    if unfinished:
        log_id = unfinished["id"]
        con.execute("UPDATE scan_log SET started_at=? WHERE id=?", (t0, log_id))
    else:
        cur = con.execute("INSERT INTO scan_log(started_at) VALUES (?)", (t0,))
        log_id = cur.lastrowid

    seen_ids = set()
    added = updated = 0
    # 现有账本: path -> (id, size, mtime)
    ledger = {r["path"]: (r["id"], r["size"], r["mtime"])
              for r in con.execute("SELECT id, path, size, mtime FROM files")}

    for root in dirs:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                size, mtime = st.st_size, st.st_mtime
                name = fn
                ext = os.path.splitext(fn)[1].lower()

                old = ledger.get(p)
                if old and old[1] == size and old[2] == mtime:
                    seen_ids.add(old[0])
                    continue  # 未变,跳过

                # 新增或变化:提文本 + 指纹
                res = extmod.extract(p) if ext in SUPPORTED_EXTS else \
                    extmod.ExtractResult([], "", "failed", f"暂不支持的内容格式: {ext or '(无扩展名)'}")
                sha = _sha256(p)
                fp = shmod.simhash(res.text) if res.text.strip() else None

                if old:  # 更新
                    fid = old[0]
                    con.execute(
                        """UPDATE files SET name=?, ext=?, size=?, mtime=?, sha256=?,
                                  simhash=?, text_len=?, status=?, status_reason=?, indexed_at=?
                           WHERE id=?""",
                        (name, ext, size, mtime, sha, fp, len(res.text),
                         res.status, res.reason, t0, fid))
                    _index_text(con, fid, res.text)
                    updated += 1
                else:  # 新增
                    cur = con.execute(
                        """INSERT INTO files(path,name,ext,size,mtime,sha256,simhash,
                                            text_len,status,status_reason,indexed_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (p, name, ext, size, mtime, sha, fp, len(res.text),
                         res.status, res.reason, t0))
                    fid = cur.lastrowid
                    _index_text(con, fid, res.text)
                    added += 1
                seen_ids.add(fid)
                if progress:
                    if not progress(p, res.status):
                        raise InterruptedError("用户取消扫描")

    # 失踪文件标记
    missing = 0
    for r in con.execute("SELECT id, path FROM files WHERE status != 'missing'"):
        if r["id"] not in seen_ids:
            con.execute("UPDATE files SET status='missing', status_reason='扫描时未找到,可能已移动/改名/删除' WHERE id=?",
                        (r["id"],))
            missing += 1

    con.execute("UPDATE scan_log SET finished_at=?, added=?, updated=?, missing=? WHERE id=?",
                (dbmod.now(), added, updated, missing, log_id))
    con.commit()
    return {"added": added, "updated": updated, "missing": missing}
