"""空桩：网点时钟漂移

契约（邻题实现时必须遵守）：
- 网点上报时钟与仓时钟偏差超过阈值时进旁路
- 不得改坏基线默认关窗 happy path（事件时入窗 → 关窗物化 → 贯验）。
- 页面须能读到：当前策略名、命运变化、可点的下一步。

扩展切口：
- 装载前后钩子：before_load / after_load
- 入窗判定钩子：decide_window
- 关窗前后钩子：before_close / after_close
- 贯验扩展：extra_verify_checks
"""

NAME = "网点时钟漂移"
CONTRACT = "网点上报时钟与仓时钟偏差超过阈值时进旁路"

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
        "默认启用": False,
        "说明": "基线不调用本空桩；邻题导入后自行接线",
    }


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
    """附加贯验检查，返回错误文案列表；空列表表示通过。"""
    return []
