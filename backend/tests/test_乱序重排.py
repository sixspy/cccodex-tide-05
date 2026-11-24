"""乱序重排入窗：乱序两笔 / 正序对照 / 切片事件序 / 关窗并发 / 重排写缓冲同成败。"""
from pathlib import Path
import json
import os
import tempfile
import threading

import pytest

_tmp = tempfile.mkdtemp()
os.environ["数据目录"] = _tmp
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

from app import seed
from app.db import 连接
from app.modules import 乱序重排入窗 as 重排
from app.services import 夹具, 关窗, 贯验, 目录, 装载

清表 = ("观测点", "入窗缓冲", "窗切片账", "迟到匣", "窗贯验", "装载批次", "关窗批次", "到达归档")


def _清库():
    conn = 连接()
    try:
        for t in 清表:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _db():
    seed.初始化库()
    _清库()
    yield
    _清库()


def _在缓冲(运单键):
    return [
        r for r in 目录.缓冲列表()
        if r["运单键"] == 运单键 and r["命运"] == "在缓冲"
    ]


def _视图(运单键):
    行 = [r for r in 重排.重排视图() if r["运单键"] == 运单键]
    assert len(行) == 1
    return 行[0]


def test_乱序两笔_现行首条较早事件时():
    # 夹具乱序样例：E-ord-2(00:50) 先到达，E-ord-1(00:05) 后到达
    报告 = 装载.装一批(夹具.读取("乱序样例"))
    assert 报告["入缓冲"] == 2

    缓冲 = _在缓冲("运单-D")
    assert len(缓冲) == 2
    # 现行首条须是事件时较早的那笔，且与次条可区分
    assert 缓冲[0]["事件编号"] == "E-ord-1"
    assert 缓冲[0]["事件时"] == "2026-11-24T00:05:00Z"
    assert 缓冲[0]["事件时"] < 缓冲[1]["事件时"]
    assert [r["序位"] for r in 缓冲] == [1, 2]
    assert 缓冲[0]["形态标记"] == "乱序重排"

    # 只读接口：运单键、首事件时、形态标记、valid
    视 = _视图("运单-D")
    assert 视["首事件时"] == "2026-11-24T00:05:00Z"
    assert 视["到达首事件时"] == "2026-11-24T00:50:00Z"  # 到达轨首条，可区分谁更早
    assert 视["形态标记"] == "乱序重排"
    assert 视["valid"] is True

    # 双写两轨：只读归档保留到达序
    conn = 连接()
    try:
        归档 = conn.execute(
            "SELECT 事件编号 FROM 到达归档 WHERE 运单键=? ORDER BY 编号", ("运单-D",)
        ).fetchall()
    finally:
        conn.close()
    assert [r["事件编号"] for r in 归档] == ["E-ord-2", "E-ord-1"]


def test_正序对照():
    报告 = 装载.装一批({"事件": [
        {"事件编号": "E-z1", "运单键": "运单-Z", "网点键": "网点-东站", "事件时": "2026-11-24T00:10:00Z"},
        {"事件编号": "E-z2", "运单键": "运单-Z", "网点键": "网点-西港", "事件时": "2026-11-24T00:20:00Z"},
    ]})
    assert 报告["入缓冲"] == 2

    缓冲 = _在缓冲("运单-Z")
    assert [r["事件编号"] for r in 缓冲] == ["E-z1", "E-z2"]
    assert [r["序位"] for r in 缓冲] == [1, 2]
    assert 缓冲[0]["形态标记"] == "正序"

    视 = _视图("运单-Z")
    assert 视["首事件时"] == "2026-11-24T00:10:00Z"
    assert 视["到达首事件时"] == "2026-11-24T00:10:00Z"
    assert 视["形态标记"] == "正序"
    assert 视["valid"] is True


def test_跨批乱序_续到重排序位():
    装载.装一批({"事件": [
        {"事件编号": "E-k2", "运单键": "运单-K", "网点键": "网点-东站", "事件时": "2026-11-24T00:30:00Z"},
    ]})
    装载.装一批({"事件": [
        {"事件编号": "E-k1", "运单键": "运单-K", "网点键": "网点-西港", "事件时": "2026-11-24T00:05:00Z"},
    ]})
    缓冲 = _在缓冲("运单-K")
    assert [r["事件编号"] for r in 缓冲] == ["E-k1", "E-k2"]
    assert [r["序位"] for r in 缓冲] == [1, 2]
    assert _视图("运单-K")["形态标记"] == "乱序重排"


def test_关窗切片事件序():
    装载.装一批(夹具.读取("乱序样例"))
    关 = 关窗.关当前窗()
    assert 关["成片数"] == 1

    切片 = [r for r in 目录.切片列表() if r["运单键"] == "运单-D"]
    assert len(切片) == 1
    片 = 切片[0]
    assert 片["事件数"] == 2
    assert 片["首事件时"] == "2026-11-24T00:05:00Z"
    assert 片["形态标记"] == "乱序重排"
    assert json.loads(片["事件序"]) == ["E-ord-1", "E-ord-2"]
    assert 贯验.跑一次()["是否对齐"] is True


def test_关窗并发不得双序片():
    装载.装一批(夹具.读取("乱序样例"))      # 运单-D ×2
    装载.装一批(夹具.读取("窗内成片样例"))  # 运单-A ×2、运单-B ×1

    结果 = []
    def 跑():
        结果.append(关窗.关当前窗())
    线程 = [threading.Thread(target=跑) for _ in range(2)]
    for t in 线程:
        t.start()
    for t in 线程:
        t.join()

    # 两路关窗不得双成功：成片总数 = 运单数，不得双序片
    assert sum(r["成片数"] for r in 结果) == 3
    切片 = 目录.切片列表()
    assert len(切片) == 3
    assert sorted(r["运单键"] for r in 切片) == ["运单-A", "运单-B", "运单-D"]
    assert sum(r["事件数"] for r in 切片) == 5
    assert 贯验.跑一次()["是否对齐"] is True


def test_重排写缓冲同成败(monkeypatch):
    装载.装一批({"事件": [
        {"事件编号": "E-a1", "运单键": "运单-A1", "网点键": "网点-东站", "事件时": "2026-11-24T00:10:00Z"},
    ]})

    原 = 重排.重排写缓冲
    def 炸(*a, **k):
        原(*a, **k)  # 先真写一笔，再炸：验证整体回滚
        raise RuntimeError("物化中断")
    monkeypatch.setattr(重排, "重排写缓冲", 炸)

    with pytest.raises(RuntimeError):
        装载.装一批({"事件": [
            {"事件编号": "E-a2", "运单键": "运单-A1", "网点键": "网点-西港", "事件时": "2026-11-24T00:05:00Z"},
        ]})

    conn = 连接()
    try:
        assert conn.execute("SELECT COUNT(*) AS c FROM 观测点 WHERE 事件编号='E-a2'").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) AS c FROM 入窗缓冲 WHERE 事件编号='E-a2'").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) AS c FROM 到达归档 WHERE 事件编号='E-a2'").fetchone()["c"] == 0
        # 既有行不受半截重排影响
        行 = conn.execute("SELECT 序位 FROM 入窗缓冲 WHERE 事件编号='E-a1'").fetchone()
        assert 行["序位"] == 1
    finally:
        conn.close()
