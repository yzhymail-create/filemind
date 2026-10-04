#!/usr/bin/env python3
"""删除策略:只进 Windows 回收站,不彻底删除.

失败时直接返回原因,绝不把文件挪到别处(不做 .filemind_trash 之类兜底),
让用户明确知道没删成,而不是"以为进了回收站其实被藏起来了".
"""
from __future__ import annotations

import os


def to_recycle(path: str) -> tuple:
    """把文件移入 Windows 回收站.

    返回 (True, "") 或 (False, 原因).
    """
    try:
        from send2trash import send2trash
    except ImportError as e:
        return False, f"send2trash 未安装或不可用: {e}"
    if not os.path.exists(path):
        return False, "文件已不存在(可能已被移动或删除)"
    try:
        send2trash(path)
    except Exception as e:  # noqa: BLE001 - 需要把真实原因告诉用户
        return False, f"移入回收站失败: {e}"
    if os.path.exists(path):
        return False, "文件仍在原位置,可能被其他程序占用或权限不足"
    return True, ""
