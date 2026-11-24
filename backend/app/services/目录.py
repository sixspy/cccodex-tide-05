"""列表与窗规读写。"""
from __future__ import annotations
from app.db import 连接


def 窗规() -> dict:
    conn = 连接()
    try:
        rows = conn.execute("SELECT 键,值 FROM 窗规").fetchall()
        return {r["键"]: r["值"] for r in rows}
    finally:
        conn.close()


def 改窗规(体: dict) -> dict:
    conn = 连接()
    try:
        for k, v in (体 or {}).items():
            conn.execute(
                "INSERT INTO 窗规(键,值) VALUES (?,?) ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
                (str(k), str(v)),
            )
        conn.commit()
        return 窗规()
    finally:
        conn.close()


def 网点列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 网点源 ORDER BY 源键").fetchall()]
    finally:
        conn.close()


def 观测列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 观测点 ORDER BY 事件时 DESC LIMIT 200").fetchall()]
    finally:
        conn.close()


def 缓冲列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 入窗缓冲 ORDER BY 事件时").fetchall()]
    finally:
        conn.close()


def 切片列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 窗切片账 ORDER BY 物化时 DESC LIMIT 200").fetchall()]
    finally:
        conn.close()


def 迟到列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 迟到匣 ORDER BY 编号 DESC LIMIT 200").fetchall()]
    finally:
        conn.close()


def 贯验列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 窗贯验 ORDER BY 编号 DESC LIMIT 50").fetchall()]
    finally:
        conn.close()


def 概览() -> dict:
    conn = 连接()
    try:
        return {
            "观测点": conn.execute("SELECT COUNT(*) AS c FROM 观测点").fetchone()["c"],
            "在缓冲": conn.execute("SELECT COUNT(*) AS c FROM 入窗缓冲 WHERE 命运='在缓冲'").fetchone()["c"],
            "窗切片": conn.execute("SELECT COUNT(*) AS c FROM 窗切片账").fetchone()["c"],
            "迟到": conn.execute("SELECT COUNT(*) AS c FROM 迟到匣").fetchone()["c"],
            "窗规": 窗规(),
        }
    finally:
        conn.close()
