import re
from datetime import datetime

STATION = re.compile(r"^[A-Z]{2}\d{2}$")
LINE_NO = re.compile(r"^\d+$")
FLAGS = {"A": "实测", "M": "插补", "B": "可疑"}


def parse_telegram_line(line: str):
    """解析一行报文（不负责行号，仅校验四段数据列）。

    四段式：站码|十二位时刻|潮位厘米|质量旗
    五段式：行号|站码|时刻|潮位|质量旗，行号段为正整数或 "-"（表示行号缺失）。
    返回 (parsed, reason)；reason 非空表示解析失败。
    """
    parts = [part.strip() for part in line.strip().split("|")]
    if len(parts) not in (4, 5):
        return None, "列数不是四段或五段"
    if len(parts) == 5:
        line_no_text, station, stamp, tide, flag = parts
        if line_no_text != "-" and not LINE_NO.fullmatch(line_no_text):
            return None, "首段行号应为正整数或缺失符 -"
    else:
        station, stamp, tide, flag = parts
    if not STATION.match(station):
        return None, "站码应为两位字母加两位数字"
    try:
        observed = datetime.strptime(stamp, "%Y%m%d%H%M")
    except ValueError:
        return None, "时间不是十二位数字"
    if not re.fullmatch(r"-?\d+", tide):
        return None, "潮位不是整数厘米"
    centimeters = int(tide)
    if centimeters < -500 or centimeters > 2000:
        return None, "潮位超出量程"
    if flag not in FLAGS:
        return None, "质量旗不在 A、M、B"
    return {
        "station_code": station,
        "observed_at": observed,
        "tide_cm": centimeters,
        "quality_flag": flag,
        "flag_label": FLAGS[flag],
    }, None


def parse_with_line_no(line: str, physical_line_no: int):
    """结合物理行号解析，返回 (line_no, parsed, reason)。

    line_no 为 None 表示这一行行号缺失（五段式且首段是 "-"），
    缺失行不参与批内重行比较；解析失败时 parsed 为 None。
    """
    parts = [part.strip() for part in line.strip().split("|")]
    parsed, reason = parse_telegram_line(line)
    if reason:
        # 失败时也尽量给出可用行号，便于 reject_rows 定位
        line_no = physical_line_no
        if len(parts) == 5:
            if parts[0] == "-":
                line_no = None
            elif LINE_NO.fullmatch(parts[0]):
                line_no = int(parts[0])
        return line_no, None, reason

    if len(parts) == 5:
        line_no = None if parts[0] == "-" else int(parts[0])
    else:
        line_no = physical_line_no
    return line_no, parsed, reason
