#!/usr/bin/env python3
"""内容记忆搜索:FTS5(trigram)关键词检索,结果按版本链聚合.

查询处理(规则式,无 AI):
  空格分词 -> 每段做 trigram 短语子串匹配 -> AND 组合.
  "去年"等时间词 -> mtime 过滤(本期仅支持:去年/今年/近30天).
"""
from __future__ import annotations

import datetime
import re

from . import db as dbmod
from . import recommend as recmod

_TIME_PAT = [
    (re.compile(r"去年"), lambda: (datetime.date.today().year - 1, None)),
    (re.compile(r"今年"), lambda: (datetime.date.today().year, None)),
    (re.compile(r"近 ?30 ?天"), lambda: (None, 30)),
]


def _split_time(query: str):
    year, days = None, None
    for pat, fn in _TIME_PAT:
        if pat.search(query):
            query = pat.sub("", query)
            y, d = fn()
            year, days = y or year, d or days
    return query.strip(), year, days


def _fts_query(query: str):
    """长词(>=3字)走 FTS trigram;短词退化为 LIKE 子串过滤."""
    terms = [t.replace('"', "") for t in query.split() if t.strip()]
    long_terms = [t for t in terms if len(t) >= 3]
    short_terms = [t for t in terms if len(t) < 3]
    fts_q = " AND ".join('"%s"' % t for t in long_terms)
    return fts_q, short_terms


def search_grouped(db_path: str, query: str, limit: int = 50) -> dict:
    query, year, days = _split_time(query)
    fq, short_terms = _fts_query(query)
    con = dbmod.connect(db_path)
    groups = {}
    order = []
    if fq or short_terms:
        like_sql = "".join(" AND text LIKE ?" for _ in short_terms)
        like_params = ["%%%s%%" % t for t in short_terms]
        try:
            if fq:
                sql = """SELECT f.id, f.name, f.path, f.mtime, f.ext,
                                snippet(fts_docs, 1, '<b>', '</b>', '…', 10) AS snip,
                                rank AS r
                         FROM fts_docs JOIN files f ON f.id = fts_docs.file_id
                         WHERE fts_docs MATCH ? AND f.status != 'missing'""" + like_sql + """
                         ORDER BY r LIMIT ?"""
                rows = con.execute(sql, [fq] + like_params + [limit]).fetchall()
            else:
                # 全是短词:退化为全文 LIKE 扫描(个人语料规模可接受)
                sql = """SELECT f.id, f.name, f.path, f.mtime, f.ext,
                                substr(text, 1, 120) AS snip, 0 AS r
                         FROM fts_docs JOIN files f ON f.id = fts_docs.file_id
                         WHERE f.status != 'missing'""" + like_sql + """
                         LIMIT ?"""
                rows = con.execute(sql, like_params + [limit]).fetchall()
        except Exception:
            rows = []
        for r in rows:
            d = dict(r)
            if year and not (d["mtime"] and datetime.datetime.fromtimestamp(d["mtime"]).year == year):
                continue
            if days and not (d["mtime"] and (dbmod.now() - d["mtime"]) <= days * 86400):
                continue
            ch = con.execute("SELECT chain_id FROM chain_members WHERE file_id=?",
                             (d["id"],)).fetchone()
            gid = f"c{ch['chain_id']}" if ch else f"f{d['id']}"
            if gid not in groups:
                groups[gid] = {"chain_id": ch["chain_id"] if ch else None,
                               "hits": [], "best_rank": d["r"]}
                order.append(gid)
            groups[gid]["hits"].append(d)
            groups[gid]["best_rank"] = min(groups[gid]["best_rank"], d["r"])
    # 每组取推荐版本
    result = []
    for gid in sorted(order, key=lambda g: groups[g]["best_rank"]):
        g = groups[gid]
        rec = None
        if g["chain_id"]:
            rec = recmod.recommend(db_path, g["chain_id"])
            n_members = con.execute("SELECT COUNT(*) c FROM chain_members WHERE chain_id=?",
                                    (g["chain_id"],)).fetchone()["c"]
        else:
            n_members = 1
        result.append({"key": gid, "chain_id": g["chain_id"], "hits": g["hits"],
                       "recommend": rec, "n_members": n_members})
    con.close()
    return {"groups": result, "query": query}
