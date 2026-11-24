from pathlib import Path
import os
import tempfile
import pytest

_tmp = tempfile.mkdtemp()
os.environ["数据目录"] = _tmp
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

from app import seed
from app.services import 装载, 关窗, 贯验, 目录, 时间, 校验, 夹具


@pytest.fixture(autouse=True)
def _db():
    seed.初始化库()
    yield


def test_窗内装载入缓冲():
    报告 = 装载.装一批({
        "批次编号": "t1",
        "事件": [{
            "事件编号": "t-e1",
            "运单键": "运单-T",
            "网点键": "网点-东站",
            "事件时": "2026-11-24T00:15:00Z",
        }],
    })
    assert 报告["入缓冲"] == 1
    assert any(x["命运"] == "在缓冲" for x in 目录.缓冲列表())


def test_关窗物化与贯验():
    装载.装一批({
        "事件": [
            {"事件编号": "t-e2", "运单键": "运单-U", "网点键": "网点-西港", "事件时": "2026-11-24T00:25:00Z"},
            {"事件编号": "t-e3", "运单键": "运单-U", "网点键": "网点-东站", "事件时": "2026-11-24T00:35:00Z"},
        ]
    })
    关 = 关窗.关当前窗()
    assert 关["成片数"] >= 1
    验 = 贯验.跑一次()
    assert 验["是否对齐"] is True


def test_迟到进匣():
    报告 = 装载.装一批({
        "事件": [{
            "事件编号": "t-late",
            "运单键": "运单-V",
            "网点键": "网点-北仓",
            "事件时": "2026-11-24T03:00:00Z",
        }]
    })
    assert 报告["迟到"] == 1
    assert 目录.迟到列表()


def test_夹具窗内成片():
    体 = 夹具.读取("窗内成片样例")
    报告 = 装载.装一批(体)
    assert 报告["入缓冲"] == 3
    关 = 关窗.关当前窗()
    assert 关["成片数"] == 2  # 运单-A / 运单-B
    assert 贯验.跑一次()["是否对齐"] is True


def test_校验拒空白运单键():
    错 = 校验.校验事件({
        "事件编号": "x",
        "运单键": "坏 键",
        "网点键": "网点-东站",
        "事件时": "2026-11-24T00:01:00Z",
    })
    assert any("空白" in e for e in 错)


def test_推进窗():
    a, b = 时间.推进窗("2026-11-24T00:00:00Z", "2026-11-24T01:00:00Z")
    assert a == "2026-11-24T01:00:00Z"
    assert b == "2026-11-24T02:00:00Z"


def test_幂等驳回():
    体 = {
        "事件": [{
            "事件编号": "dup-1",
            "运单键": "运单-Z",
            "网点键": "网点-东站",
            "事件时": "2026-11-24T00:11:00Z",
        }]
    }
    assert 装载.装一批(体)["入缓冲"] == 1
    assert 装载.装一批(体)["驳回"] == 1
