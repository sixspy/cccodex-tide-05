"""关窗：缓冲按运单物化为窗切片。"""
from __future__ import annotations
import json
import uuid
from collections import defaultdict
from app.db import 连接
from app.seed import 此刻
from app.services import 目录


def 关当前窗() -> dict:
    规 = 目录.窗规()
    窗号 = 规.get("当前窗号", "W-demo")
    窗起 = 规.get("窗起", "")
    窗止 = 规.get("窗止", "")
    批 = f"关窗-{uuid.uuid4().hex[:8]}"
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT * FROM 入窗缓冲 WHERE 窗号=? AND 命运='在缓冲'", (窗号,)
        ).fetchall()
        by_waybill: dict[str, list] = defaultdict(list)
        for r in rows:
            by_waybill[r["运单键"]].append(r)
        成片 = 0
        时刻 = 此刻()
        for 运单, evs in by_waybill.items():
            切片 = f"片-{窗号}-{运单}-{uuid.uuid4().hex[:6]}"
            conn.execute(
                """INSERT INTO 窗切片账(切片编号,窗号,运单键,事件数,窗起,窗止,物化时,命运)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (切片, 窗号, 运单, len(evs), 窗起, 窗止, 时刻, "已成片"),
            )
            for e in evs:
                conn.execute(
                    "UPDATE 入窗缓冲 SET 命运=? WHERE 事件编号=?",
                    ("已物化", e["事件编号"]),
                )
                conn.execute(
                    "UPDATE 观测点 SET 命运=? WHERE 事件编号=?",
                    ("已成片", e["事件编号"]),
                )
            成片 += 1
        报告 = {"批次编号": 批, "窗号": 窗号, "成片数": 成片, "缓冲消耗": len(rows)}
        conn.execute(
            """INSERT INTO 关窗批次(编号,窗号,时刻,成片数,报告) VALUES (?,?,?,?,?)""",
            (批, 窗号, 时刻, 成片, json.dumps(报告, ensure_ascii=False)),
        )
        conn.commit()
        return 报告
    finally:
        conn.close()
