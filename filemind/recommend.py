#!/usr/bin/env python3
"""可用版本推荐:只推荐、不自动定;每次推荐必须附理由.

信号权重(默认保守):
  用户人工置顶            +100   (最强,压倒一切)
  文件名含 最终/终版/定稿   +30
  文件名含 确认/审定       +25
  文件名含 发布/归档       +20
  文件名含 草稿/初稿       -10
  链尾(最新)且之后无实质修改 +10
"""
from __future__ import annotations

import re

from . import db as dbmod
from . import simhash as shmod

_FINAL = re.compile(r"最终|终版|定稿")
_CONFIRM = re.compile(r"确认|审定")
_PUBLISH = re.compile(r"发布|归档")
_DRAFT = re.compile(r"草稿|初稿")


def recommend(db_path: str, chain_id: int) -> dict:
    con = dbmod.connect(db_path)
    members = con.execute(
        """SELECT m.file_id, m.order_no, f.name, f.path, f.mtime, f.simhash
           FROM chain_members m JOIN files f ON f.id = m.file_id
           WHERE m.chain_id = ? ORDER BY m.order_no""", (chain_id,)).fetchall()
    members = [dict(r) for r in members]
    if not members:
        con.close()
        return {"file_id": None, "reasons": ["空链"]}

    pinned = {r["file_id"] for r in con.execute(
        "SELECT file_id FROM user_marks WHERE kind='pinned'")}
    tail = members[-1]

    scored = []
    for m in members:
        score, reasons = 0, []
        if m["file_id"] in pinned:
            score += 100
            reasons.append("你人工置顶为可用版本")
        nm = m["name"]
        if _FINAL.search(nm):
            score += 30
            reasons.append("文件名含'最终/终版/定稿'标记")
        if _CONFIRM.search(nm):
            score += 25
            reasons.append("文件名含'确认/审定'标记")
        if _PUBLISH.search(nm):
            score += 20
            reasons.append("文件名含'发布/归档'标记")
        if _DRAFT.search(nm):
            score -= 10
            reasons.append("文件名含'草稿/初稿'标记")
        if m["file_id"] == tail["file_id"]:
            # 链尾:检查相对上一版是否有实质修改
            if len(members) >= 2 and m["simhash"] is not None and members[-2]["simhash"] is not None:
                d = shmod.hamming(m["simhash"], members[-2]["simhash"])
                if d <= 3:
                    score += 10
                    reasons.append("链尾版本,与上一版几乎无实质修改")
                else:
                    reasons.append("链尾版本,但与上一版有实质修改,请确认")
            else:
                score += 10
                reasons.append("链尾(最新修改)版本")
        scored.append((score, m["order_no"], m, reasons))

    scored.sort(key=lambda t: (-t[0], -t[1]))
    best = scored[0]
    con.close()
    return {"file_id": best[2]["file_id"], "name": best[2]["name"],
            "path": best[2]["path"], "score": best[0], "reasons": best[3]}


def recommend_dup_keep(db_path: str, group: list) -> dict:
    """精确去重组:推荐保留哪一个,附理由(路径规范性 + 最新)."""
    def key(g):
        depth = g["path"].count("\\") + g["path"].count("/")
        return (depth, -(g["mtime"] or 0))
    best = sorted(group, key=key)[0]
    reasons = ["路径层级最浅、位置最规范" if best == sorted(group, key=key)[0] else ""]
    reasons.append("同组中修改时间最新" if best["mtime"] == max(g["mtime"] or 0 for g in group) else "")
    return {"keep": best, "reasons": [r for r in reasons if r]}
