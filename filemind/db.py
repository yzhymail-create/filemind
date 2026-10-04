#!/usr/bin/env python3
"""SQLite 存储层:文件账本 + FTS5 全文索引 + 版本链 + 用户标记.

设计原则:原始文件是主数据,这里只存"认知"(索引/关系/标记),不存文件快照.
"""
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
    id            INTEGER PRIMARY KEY,
    path          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    ext           TEXT NOT NULL,
    size          INTEGER,
    mtime         REAL,
    sha256        TEXT,
    simhash       INTEGER,
    text_len      INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'pending',   -- ok | partial | failed | skipped
    status_reason TEXT DEFAULT '',
    indexed_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_files_sha ON files(sha256);
CREATE INDEX IF NOT EXISTS idx_files_dir ON files(path);

-- 全文索引:trigram 分词,中英文都不需要额外分词器
CREATE VIRTUAL TABLE IF NOT EXISTS fts_docs
    USING fts5(file_id UNINDEXED, text, tokenize='trigram');

CREATE TABLE IF NOT EXISTS chains(
    id         INTEGER PRIMARY KEY,
    created_at REAL,
    confirmed  INTEGER DEFAULT 0,   -- 0=算法自动,1=用户已确认
    note       TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chain_members(
    chain_id   INTEGER,
    file_id    INTEGER UNIQUE,
    order_no   INTEGER,
    confidence REAL,
    PRIMARY KEY(chain_id, file_id)
);
CREATE TABLE IF NOT EXISTS user_marks(
    file_id    INTEGER,
    kind       TEXT,                 -- pinned=设为可用版 | excluded=从链排除
    note       TEXT DEFAULT '',
    created_at REAL,
    PRIMARY KEY(file_id, kind)
);
CREATE TABLE IF NOT EXISTS scan_log(
    id         INTEGER PRIMARY KEY,
    started_at REAL,
    finished_at REAL,
    added      INTEGER DEFAULT 0,
    updated    INTEGER DEFAULT 0,
    missing    INTEGER DEFAULT 0
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.executescript(SCHEMA)
    return con


def check_fts5_trigram(con: sqlite3.Connection) -> bool:
    """Windows 自带 Python 的 sqlite 是否支持 FTS5+trigram,启动时自检."""
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_check USING fts5(x, tokenize='trigram')")
        con.execute("DROP TABLE _fts_check")
        return True
    except sqlite3.Error:
        return False


def now() -> float:
    return time.time()
