"""夹具读写。"""
from __future__ import annotations
import json
from pathlib import Path
from app.db import 夹具目录


def 列表() -> list[str]:
    if not 夹具目录.is_dir():
        return []
    return sorted(p.stem for p in 夹具目录.glob("*.json"))


def 读取(名: str) -> dict:
    p = 夹具目录 / f"{名}.json"
    if not p.is_file():
        raise FileNotFoundError(名)
    return json.loads(p.read_text(encoding="utf-8"))
