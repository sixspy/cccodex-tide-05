"""窗号与事件时工具。"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone


def 解析时(s: str) -> datetime:
    s = (s or "").replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def 在窗内(事件时: str, 窗起: str, 窗止: str) -> bool:
    t = 解析时(事件时)
    a = 解析时(窗起)
    b = 解析时(窗止)
    return a <= t < b


def 窗长秒(窗起: str, 窗止: str) -> int:
    return int((解析时(窗止) - 解析时(窗起)).total_seconds())


def 推进窗(窗起: str, 窗止: str, 秒: int | None = None) -> tuple[str, str]:
    a = 解析时(窗起)
    b = 解析时(窗止)
    span = 秒 if 秒 is not None else int((b - a).total_seconds())
    na = b
    nb = b + timedelta(seconds=span)
    return (
        na.strftime("%Y-%m-%dT%H:%M:%SZ"),
        nb.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def 比较事件序(a: str, b: str) -> int:
    ta, tb = 解析时(a), 解析时(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def 格式窗号(前缀: str, 窗起: str) -> str:
    t = 解析时(窗起)
    return f"{前缀}-{t.strftime('%Y%m%d-%H')}"


def 是否跨日界(窗起: str, 事件时: str) -> bool:
    return 解析时(窗起).date() != 解析时(事件时).date()
