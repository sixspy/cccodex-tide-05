import re
from datetime import datetime

STATION = re.compile(r"^[A-Z]{2}\d{2}$")
FLAGS = {"A": "实测", "M": "插补", "B": "可疑"}


def parse_telegram_line(line: str):
    parts = [part.strip() for part in line.strip().split("|")]
    if len(parts) != 4:
        return None, "列数不是四段"
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
