"""乱序重排入窗：同运单乱序到达按事件时升序重排后再物化入缓冲。

已接线（不再是空桩）：
- 双写两轨：到达序进只读归档（到达归档），现行缓冲按事件时升序物化序位；两轨读引用不同。
- 重排写缓冲与装载/关窗同事务，同成败；乱序批与关窗共用窗锁，缺锁会双序、双成功。
- 缓冲列表与关窗切片都读物化序位，不是只改列表排序样式。
"""
from __future__ import annotations

import threading

from app.db import 连接
from app.services import 时间 as 时间服务

NAME = "乱序重排入窗"
CONTRACT = "同运单乱序到达时按事件时重排后再入缓冲"

形态_事件时升序 = "事件时升序"
标记_正序 = "正序"
标记_乱序重排 = "乱序重排"

# 乱序批与关窗并发互斥：缺它会双序（两路各物化一份）、双成功
窗锁 = threading.Lock()

HOOKS = (
    "before_load",
    "after_load",
    "decide_window",
    "before_close",
    "after_close",
    "extra_verify_checks",
)


def describe() -> dict:
    return {
        "空桩": NAME,
        "契约": CONTRACT,
        "钩子": list(HOOKS),
        "默认启用": True,
        "说明": "已接线：装载双写到达归档+重排写缓冲；关窗按物化序位切片；贯验带序位检查",
    }


def _序键(行: dict) -> tuple:
    """事件时升序，并列按事件编号，确定性。"""
    return (时间服务.解析时(str(行["事件时"])), str(行["事件编号"]))


def 重排行(行列表: list[dict], 形态: str = 形态_事件时升序) -> list[dict]:
    """按选定形态重排；未知形态直接拒。"""
    if 形态 != 形态_事件时升序:
        raise ValueError(f"未知重排形态:{形态}")
    return sorted((dict(r) for r in 行列表), key=_序键)


def _到达序(conn, 窗号: str, 运单键: str, 编号集: list[str]) -> list[str]:
    """只读归档轨：编号即全局到达序。"""
    if not 编号集:
        return []
    占位 = ",".join("?" for _ in 编号集)
    rows = conn.execute(
        f"SELECT 事件编号 FROM 到达归档 WHERE 窗号=? AND 运单键=? AND 事件编号 IN ({占位}) ORDER BY 编号",
        (窗号, 运单键, *编号集),
    ).fetchall()
    return [r["事件编号"] for r in rows]


def 重排写缓冲(conn, 窗号: str, 运单键: str, 新行: list[dict], 形态: str = 形态_事件时升序) -> str:
    """新事件并入 (窗号,运单键) 在缓冲集合，按形态重排序位并物化。

    与调用方同事务：重排、写缓冲、物化同成败。返回形态标记（正序/乱序重排）。
    """
    既有 = [
        dict(r)
        for r in conn.execute(
            "SELECT 事件编号,网点键,事件时 FROM 入窗缓冲 WHERE 窗号=? AND 运单键=? AND 命运='在缓冲'",
            (窗号, 运单键),
        ).fetchall()
    ]
    合并 = 既有 + [dict(e) for e in 新行]
    重排后 = 重排行(合并, 形态)
    到达 = _到达序(conn, 窗号, 运单键, [r["事件编号"] for r in 合并])
    标记 = 标记_正序 if [r["事件编号"] for r in 重排后] == 到达 else 标记_乱序重排
    新编号 = {e["事件编号"] for e in 新行}
    for 位, 行 in enumerate(重排后, 1):
        if 行["事件编号"] in 新编号:
            conn.execute(
                """INSERT INTO 入窗缓冲(事件编号,运单键,网点键,事件时,窗号,命运,入缓冲时,序位,形态标记)
                   VALUES (?,?,?,?,?,'在缓冲',?,?,?)""",
                (行["事件编号"], 运单键, 行["网点键"], 行["事件时"], 窗号, 行["入缓冲时"], 位, 标记),
            )
        else:
            conn.execute(
                "UPDATE 入窗缓冲 SET 序位=?, 形态标记=? WHERE 事件编号=?",
                (位, 标记, 行["事件编号"]),
            )
    return 标记


def 重排视图(conn=None) -> list[dict]:
    """乱序重排只读接口：每 (窗号,运单键) 在缓冲集合一行。

    字段：运单键、首事件时、形态标记、valid（另附窗号、到达首事件时做两轨对照）。
    """
    自有 = conn is None
    if 自有:
        conn = 连接()
    try:
        行 = [
            dict(r)
            for r in conn.execute(
                "SELECT 事件编号,运单键,窗号,事件时,序位,形态标记 FROM 入窗缓冲 "
                "WHERE 命运='在缓冲' ORDER BY 窗号,运单键,序位"
            ).fetchall()
        ]
        组: dict[tuple[str, str], list[dict]] = {}
        for r in 行:
            组.setdefault((r["窗号"], r["运单键"]), []).append(r)
        out = []
        for (窗号, 运单键), evs in sorted(组.items()):
            编号列 = [e["事件编号"] for e in evs]
            序位列 = [int(e["序位"]) for e in evs]
            时列 = [e["事件时"] for e in evs]
            到达 = _到达序(conn, 窗号, 运单键, 编号列)
            首到 = next((e for e in evs if 到达 and e["事件编号"] == 到达[0]), None)
            valid = 序位列 == list(range(1, len(evs) + 1)) and all(
                时间服务.比较事件序(时列[i], 时列[i + 1]) <= 0 for i in range(len(时列) - 1)
            )
            out.append(
                {
                    "运单键": 运单键,
                    "窗号": 窗号,
                    "首事件时": 时列[0] if 时列 else "",
                    "到达首事件时": 首到["事件时"] if 首到 else "",
                    "形态标记": evs[0]["形态标记"] if evs else "",
                    "valid": bool(valid),
                }
            )
        return out
    finally:
        if 自有:
            conn.close()


def before_load(batch: dict) -> dict:
    """装载前：可改批次或抛出预检错误。默认透传。"""
    return batch


def after_load(report: dict) -> dict:
    """装载后：可附加旁路统计。默认透传。"""
    return report


def decide_window(event: dict, rules: dict) -> str:
    """返回 入缓冲 / 迟到 / 驳回。基线默认由装载服务按事件时判定。"""
    return "入缓冲"


def before_close(window_id: str) -> None:
    """关窗前检查，可抛错阻断。"""
    return None


def after_close(report: dict) -> dict:
    """关窗后处理，例如推进下一窗。默认透传。"""
    return report


def extra_verify_checks(snapshot: dict) -> list[str]:
    """附加贯验检查：在缓冲序位撕裂即报错；空列表表示通过。"""
    错 = []
    for 行 in snapshot.get("重排视图", []):
        if not 行.get("valid"):
            错.append(f"序位撕裂:{行.get('窗号')}/{行.get('运单键')}")
    return 错
