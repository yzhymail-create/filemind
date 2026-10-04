#!/usr/bin/env python3
"""版本链聚类:把"同一件事情的不同时间状态"识别成一条链.

策略(保守优先):
  1. 文件名去噪 -> 同目录同归一化词干 = 候选同组
  2. 内容指纹(simhash 汉明距离 <= 12)确认,低置信组标记"需人工确认"
  3. 按 mtime 排序成链;用户确认过的链重建时保留
"""
from __future__ import annotations

import os
import re

from . import db as dbmod
from . import simhash as shmod

HAM_THRESHOLD = 12   # 版本确认参考:<=12bits 极可能是同一文档的版本
REVIEW_HAM = 20      # 超过则在链上标记"需人工确认"(文件名相近但内容差异大)

_NOISE = [
    r"[（(]\d+[)）]",                    # (1)/(2)
    r"[-_ ]?\d{8}([-_ ]?\d{4,6})?",      # 20260928 / 20260928-1530
    r"最终版|最终|终版|定稿版|定稿",
    r"确认版|确认|审定版|审定",
    r"修改\d*|改\d*|修订\d*|更新\d*",
    r"[vV]\d+(\.\d+)*",
    r"[-_ ](改|新|修|更新|定)$",
    r"[-_ ]?副本|[-_ ]?copy",
]


def normalize_stem(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    prev = None
    while prev != stem:
        prev = stem
        for pat in _NOISE:
            stem = re.sub(pat, "", stem)
    stem = re.sub(r"[-_ ]+", "", stem).strip()
    return stem or os.path.splitext(filename)[0]


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def find_exact_dups(con) -> list:
    """sha256 完全相同的真重复分组."""
    rows = con.execute(
        "SELECT id, path, name, size, mtime, sha256 FROM files "
        "WHERE sha256 IS NOT NULL AND status != 'missing' ORDER BY sha256").fetchall()
    buckets = {}
    for r in rows:
        buckets.setdefault(r["sha256"], []).append(dict(r))
    return [g for g in buckets.values() if len(g) > 1]


def _stems_match(a: str, b: str) -> bool:
    """词干相等,或一方包含另一方且长度比>=0.5(防"方案"吸入"线束阻燃验证方案")."""
    if a == b:
        return True
    if len(a) < 2 or len(b) < 2:
        return False
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) >= 0.5
    return False


def build_chains(db_path: str) -> dict:
    con = dbmod.connect(db_path)
    try:
        return _build_chains(con)
    finally:
        con.close()


def _build_chains(con) -> dict:
    # 只重建算法自动的链,用户确认过的保留
    con.execute("DELETE FROM chain_members WHERE chain_id IN (SELECT id FROM chains WHERE confirmed=0)")
    con.execute("DELETE FROM chains WHERE confirmed=0")

    # 已确认链的成员:归属已定,不参与重建(否则主键冲突)
    locked = {r["file_id"] for r in con.execute("SELECT file_id FROM chain_members")}
    # 用户手动移出的文件:不再自动并入任何链
    excluded = {r["file_id"] for r in con.execute("SELECT file_id FROM user_marks WHERE kind='excluded'")}
    rows = con.execute(
        "SELECT id, path, name, mtime, size, simhash FROM files WHERE status != 'missing'").fetchall()
    files = [dict(r) for r in rows if r["id"] not in locked and r["id"] not in excluded]
    by_id = {f["id"]: f for f in files}

    # 候选:同目录 + 词干相等/包含;确认:词干严格相等,或内容指纹足够近
    # (防止"方案"把"线束阻燃验证方案"吸入同一条链)
    stems = {f["id"]: normalize_stem(f["name"]) for f in files}
    sims = {f["id"]: f["simhash"] for f in files}
    sizes = {f["id"]: f["size"] or 0 for f in files}
    by_dir = {}
    for f in files:
        by_dir.setdefault(os.path.dirname(f["path"]), []).append(f["id"])

    def _size_similar(a: int, b: int) -> bool:
        """大小相近(差异不超过50%)则认为是同一文件的版本."""
        sa, sb = sizes[a], sizes[b]
        if sa == 0 or sb == 0:
            return False
        ratio = min(sa, sb) / max(sa, sb)
        return ratio >= 0.5

    def _edge_ok(a: int, b: int) -> bool:
        # 词干严格相等:文件名证据最强,直接合并(内容差异大则标需确认)
        if stems[a] == stems[b]:
            return True
        # 包含式候选:仅当内容几乎一致(改名/复制)才合并,大改名靠人工
        sa, sb = sims[a], sims[b]
        if sa is not None and sb is not None:
            return shmod.hamming(sa, sb) <= 8
        # 无法提取文本的文件:用文件名 + 大小判断
        if sa is None and sb is None:
            return _size_similar(a, b)
        return False

    uf = _UF()
    for ids in by_dir.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if _stems_match(stems[ids[i]], stems[ids[j]]) and _edge_ok(ids[i], ids[j]):
                    uf.union(ids[i], ids[j])

    clusters = {}
    for f in files:
        clusters.setdefault(uf.find(f["id"]), []).append(f["id"])
    clusters = {k: v for k, v in clusters.items() if len(v) > 1}

    n_chains = n_review = 0
    for _root, ids in clusters.items():
        members = sorted((by_id[i] for i in ids), key=lambda f: (f["mtime"] or 0))
        # 置信度:相邻两两的 simhash 距离,缺文本则降档
        worst = 0
        comparable = 0
        for a, b in zip(members, members[1:]):
            if a["simhash"] is not None and b["simhash"] is not None:
                d = shmod.hamming(a["simhash"], b["simhash"])
                worst = max(worst, d)
                comparable += 1
        if comparable:
            confidence = max(0.0, 1.0 - worst / 64.0)
            need_review = worst > REVIEW_HAM
        else:
            confidence = 0.5
            need_review = True
        cur = con.execute("INSERT INTO chains(created_at, confirmed, note) VALUES (?,?,?)",
                          (dbmod.now(), 0, "需人工确认" if need_review else ""))
        cid = cur.lastrowid
        for n, m in enumerate(members):
            con.execute("INSERT INTO chain_members(chain_id, file_id, order_no, confidence) VALUES (?,?,?,?)",
                        (cid, m["id"], n, confidence))
        n_chains += 1
        n_review += 1 if need_review else 0

    con.commit()
    return {"chains": n_chains, "need_review": n_review}


def suggest_moves(db_path: str, ham_threshold: int = 6) -> list:
    """失踪文件 vs 新增文件:内容极相似但路径不同 -> 疑似改名/移动."""
    con = dbmod.connect(db_path)
    missing = [dict(r) for r in con.execute(
        "SELECT id, path, name, simhash FROM files WHERE status='missing' AND simhash IS NOT NULL")]
    alive = [dict(r) for r in con.execute(
        "SELECT id, path, name, simhash FROM files WHERE status != 'missing' AND simhash IS NOT NULL")]
    out = []
    for m in missing:
        for a in alive:
            if m["id"] == a["id"]:
                continue
            if shmod.hamming(m["simhash"], a["simhash"]) <= ham_threshold:
                out.append({"from": m["path"], "to": a["path"], "name": a["name"]})
    con.close()
    return out
