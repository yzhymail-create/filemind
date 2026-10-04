#!/usr/bin/env python3
"""内容指纹层:64 位 SimHash,回答"两个文件有多像",不回答"哪里不一样".

- 基于字符 trigram,中英文通用,无需分词器.
- 汉明距离语义(参照 file-search-on 的实测表):
    <=3  bits  typo/空白级修改
    <=9  bits  单段改写
    <=12 bits  明显改写但主体相同(版本链确认阈值)
    <=16 bits  大段共有,可能是不同文档
"""
from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")


def _tokens(text: str) -> list:
    t = _WS.sub("", text).lower()
    if len(t) < 3:
        return [t] if t else []
    return [t[i:i + 3] for i in range(len(t) - 2)]


def simhash(text: str, bits: int = 64) -> int:
    vec = [0] * bits
    for tok in _tokens(text):
        h = int(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).hexdigest(), 16)
        for i in range(bits):
            vec[i] += 1 if (h >> i) & 1 else -1
    fp = 0
    for i, v in enumerate(vec):
        if v > 0:
            fp |= (1 << i)
    # 转为有符号 64 位,适配 SQLite INTEGER
    if fp >= 1 << 63:
        fp -= 1 << 64
    return fp


def _u64(x: int) -> int:
    return x & ((1 << 64) - 1)


def hamming(a: int, b: int) -> int:
    return bin(_u64(a) ^ _u64(b)).count("1")


def similarity(a: int, b: int, bits: int = 64) -> float:
    return 1.0 - hamming(a, b) / bits
