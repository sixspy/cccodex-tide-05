"""看板统计与窗账摘要。"""
from __future__ import annotations
from collections import Counter
from app.db import 连接


def 观测命运() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 命运, COUNT(*) AS c FROM 观测点 GROUP BY 命运"
        ).fetchall()
        return {r["命运"]: r["c"] for r in rows}
    finally:
        conn.close()


def 缓冲命运() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 命运, COUNT(*) AS c FROM 入窗缓冲 GROUP BY 命运"
        ).fetchall()
        return {r["命运"]: r["c"] for r in rows}
    finally:
        conn.close()


def 按网点观测() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 网点键, COUNT(*) AS c FROM 观测点 GROUP BY 网点键"
        ).fetchall()
        return {r["网点键"]: r["c"] for r in rows}
    finally:
        conn.close()


def 按窗切片() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 窗号, COUNT(*) AS c, COALESCE(SUM(事件数),0) AS 事件数 FROM 窗切片账 GROUP BY 窗号"
        ).fetchall()
        return {
            r["窗号"]: {"切片笔数": r["c"], "事件数": r["事件数"]}
            for r in rows
        }
    finally:
        conn.close()


def 装载批次摘要(限制: int = 20) -> list[dict]:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 编号,时刻,入流,入缓冲,迟到 FROM 装载批次 ORDER BY 时刻 DESC LIMIT ?",
            (限制,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def 关窗批次摘要(限制: int = 20) -> list[dict]:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 编号,窗号,时刻,成片数 FROM 关窗批次 ORDER BY 时刻 DESC LIMIT ?",
            (限制,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def 运单事件直方图() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 运单键, COUNT(*) AS c FROM 观测点 GROUP BY 运单键"
        ).fetchall()
        return {r["运单键"]: r["c"] for r in rows}
    finally:
        conn.close()


def 计数袋(*dicts: dict) -> Counter:
    c: Counter = Counter()
    for d in dicts:
        c.update(d or {})
    return c
