"""装载字段校验与批次预检。"""
from __future__ import annotations

必填 = ("事件编号", "运单键", "网点键", "事件时")
时间样例 = "2026-11-24T00:00:00Z"


def 校验事件(ev: dict) -> list[str]:
    if not isinstance(ev, dict):
        return ["事件不是对象"]
    错: list[str] = []
    for k in 必填:
        if ev.get(k) in (None, ""):
            错.append(f"缺字段:{k}")
    键 = str(ev.get("运单键") or "").strip()
    if 键 and (" " in 键 or "	" in 键):
        错.append("运单键含空白")
    编号 = str(ev.get("事件编号") or "").strip()
    if 编号 and (" " in 编号 or "	" in 编号):
        错.append("事件编号含空白")
    事件时 = str(ev.get("事件时") or "")
    if 事件时:
        try:
            from app.services.时间 import 解析时

            解析时(事件时)
        except Exception:
            错.append("事件时无法解析")
    return 错


def 校验批次(体: dict) -> list[str]:
    if not isinstance(体, dict):
        return ["体须为对象"]
    事件 = 体.get("事件")
    if not isinstance(事件, list) or not 事件:
        return ["事件列表为空"]
    错: list[str] = []
    见: set[str] = set()
    for i, ev in enumerate(事件):
        for e in 校验事件(ev or {}):
            错.append(f"[{i}]{e}")
        编号 = str((ev or {}).get("事件编号", ""))
        if 编号 and 编号 in 见:
            错.append(f"[{i}]事件编号重复")
        if 编号:
            见.add(编号)
    return 错


def 校验窗规补丁(体: dict) -> list[str]:
    if not isinstance(体, dict):
        return ["窗规补丁须为对象"]
    错: list[str] = []
    if "窗长秒" in 体:
        try:
            if int(体["窗长秒"]) <= 0:
                错.append("窗长秒须为正整数")
        except Exception:
            错.append("窗长秒非整数")
    for k in ("窗起", "窗止"):
        if k in 体 and 体[k]:
            try:
                from app.services.时间 import 解析时

                解析时(str(体[k]))
            except Exception:
                错.append(f"{k}无法解析")
    if "窗起" in 体 and "窗止" in 体 and 体["窗起"] and 体["窗止"]:
        from app.services.时间 import 解析时

        if 解析时(str(体["窗起"])) >= 解析时(str(体["窗止"])):
            错.append("窗起须早于窗止")
    return 错


def 摘要错误(错: list[str], 上限: int = 8) -> str:
    if not 错:
        return ""
    head = 错[:上限]
    more = len(错) - len(head)
    text = "; ".join(head)
    if more > 0:
        text += f" …另有{more}条"
    return text
