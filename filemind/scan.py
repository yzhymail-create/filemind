#!/usr/bin/env python3
"""增量巡检:用 (路径, 大小, 修改时间) 账本比对,只处理新增/变化/失踪文件.

优化版本 (v2):
- 使用 os.scandir() 替代 os.walk() - 快 2-3 倍
- 多线程并行计算 SHA256 和提取文本
- 批量数据库操作减少事务开销
"""
from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from . import db as dbmod
from . import extract as extmod
from . import simhash as shmod

SUPPORTED_EXTS = {".txt", ".md", ".csv", ".log", ".ini", ".cfg",
                  ".docx", ".xlsx", ".pptx", ".pdf"}

# 并行处理线程数（根据 CPU 核心数调整）
MAX_WORKERS = min(8, os.cpu_count() or 4)

# 跳过的目录名（不区分大小写）
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".idea", ".vscode", ".vs", "dist", "build", "target",
    ".cache", ".tmp", "temp", "logs", ".log",
}

# 大文件阈值（字节），超过此大小跳过文本提取，只计算指纹
# 默认 10MB
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024


def _sha256(path: str) -> Optional[str]:
    """计算文件 SHA256"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _process_file(p: str, fn: str, ext: str, size: int, mtime: float):
    """处理单个文件：提取文本 + 计算指纹（可并行）
    
    优化：大文件（>10MB）跳过文本提取，只计算指纹
    """
    # 大文件跳过文本提取，只计算指纹
    if size > LARGE_FILE_THRESHOLD:
        res = extmod.ExtractResult([], "", "skipped", f"大文件({size // 1024 // 1024}MB)，跳过文本提取")
    elif ext in SUPPORTED_EXTS:
        res = extmod.extract(p)
    else:
        res = extmod.ExtractResult([], "", "failed", f"暂不支持的内容格式: {ext or '(无扩展名)'}")
    
    # 计算 SHA256
    sha = _sha256(p)
    
    # 计算 SimHash
    fp = shmod.simhash(res.text) if res.text.strip() else None
    
    return {
        "path": p,
        "name": fn,
        "ext": ext,
        "size": size,
        "mtime": mtime,
        "sha256": sha,
        "simhash": fp,
        "text": res.text,
        "text_len": len(res.text),
        "status": res.status,
        "reason": res.reason,
    }


def _index_text(con, file_id: int, text: str):
    """索引文件文本到 FTS"""
    con.execute("DELETE FROM fts_docs WHERE file_id=?", (file_id,))
    if text.strip():
        con.execute("INSERT INTO fts_docs(file_id, text) VALUES (?,?)", (file_id, text))


def scan(dirs: list, db_path: str, progress=None) -> dict:
    """扫描指定目录"""
    con = dbmod.connect(db_path)
    try:
        result = _scan_inner(con, dirs, progress)
        con.commit()
        return result
    except Exception as e:
        try:
            con.rollback()
        except Exception:
            pass
        raise e
    finally:
        con.close()


def _scandir_recursive(root: str, skip_dirs: set = None):
    """递归扫描目录（使用 os.scandir，比 os.walk 快）
    
    优化：跳过指定的目录（如 node_modules, .git 等）
    """
    if skip_dirs is None:
        skip_dirs = SKIP_DIRS
    
    try:
        with os.scandir(root) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False):
                    yield entry
                elif entry.is_dir(follow_symlinks=False):
                    # 跳过指定的目录
                    if entry.name.lower() not in skip_dirs:
                        yield from _scandir_recursive(entry.path, skip_dirs)
    except OSError:
        pass


def _scan_inner(con, dirs, progress) -> dict:
    """扫描内部实现（优化版）"""
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

    # 收集所有需要处理的文件（使用 os.scandir 快速遍历）
    files_to_process = []
    
    for root in dirs:
        for entry in _scandir_recursive(root):
            try:
                p = entry.path
                fn = entry.name
                ext = os.path.splitext(fn)[1].lower()
                st = entry.stat()
                size, mtime = st.st_size, st.st_mtime
            except OSError:
                continue
            
            # 检查是否变化
            old = ledger.get(p)
            if old and old[1] == size and old[2] == mtime:
                seen_ids.add(old[0])
                continue  # 未变，跳过
            
            files_to_process.append((p, fn, ext, size, mtime))

    # 多线程并行处理文件
    if files_to_process:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_process_file, p, fn, ext, size, mtime): (p, fn, ext, size, mtime)
                for p, fn, ext, size, mtime in files_to_process
            }
            
            for future in as_completed(futures):
                try:
                    file_data = future.result()
                    p = file_data["path"]
                    
                    old = ledger.get(p)
                    
                    if old:  # 更新
                        fid = old[0]
                        con.execute(
                            """UPDATE files SET name=?, ext=?, size=?, mtime=?, sha256=?,
                                      simhash=?, text_len=?, status=?, status_reason=?, indexed_at=?
                               WHERE id=?""",
                            (file_data["name"], file_data["ext"], file_data["size"], file_data["mtime"],
                             file_data["sha256"], file_data["simhash"], file_data["text_len"],
                             file_data["status"], file_data["reason"], t0, fid))
                        _index_text(con, fid, file_data["text"])
                        updated += 1
                    else:  # 新增
                        cur = con.execute(
                            """INSERT INTO files(path,name,ext,size,mtime,sha256,simhash,
                                                text_len,status,status_reason,indexed_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                            (p, file_data["name"], file_data["ext"], file_data["size"], file_data["mtime"],
                             file_data["sha256"], file_data["simhash"], file_data["text_len"],
                             file_data["status"], file_data["reason"], t0))
                        fid = cur.lastrowid
                        _index_text(con, fid, file_data["text"])
                        added += 1
                    
                    seen_ids.add(fid)
                    
                    # 进度回调
                    if progress:
                        if not progress(p, file_data["status"]):
                            executor.shutdown(wait=False)
                            raise InterruptedError("用户取消扫描")
                
                except Exception as e:
                    # 单个文件处理失败，继续处理其他文件
                    if progress:
                        progress(futures[future][0], f"error: {e}")

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
