"""并发场景测试：模拟三名工程师同时更新不同产品的针卡数据（需求 3）。

SQLite 在共享盘上是文件锁排队写入；每个线程持有独立连接（等价于独立客户端进程），
重点验证：① 不同产品并发写入全部成功且数据完整；② 最坏情况（同卡并发）不丢不坏；
③ 并发混合操作（数据点+状态流转+设置修改）保持一致。
"""

from __future__ import annotations

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.app_context import AppContext  # noqa: E402

N_WRITES = 25


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "conc.db")
    ctx = AppContext(path)  # 主线程初始化 schema/默认值/内置账号
    for i in range(3):
        pid = ctx.products_repo.create({
            "name": f"P{i}", "touches_per_wafer": 17146, "wph": 60,
            "initial_len_um": 30.0, "rated_touches": 4800000,
            "lead_time_days": 30, "note": "",
        })
        ctx.cards.create_card("setup", f"RR-{i}", [pid])
    return path


def test_three_engineers_update_different_products(db_path):
    """三人同时更新不同产品的卡：每人 25 条 × 3 人 = 75 条，全部成功、互不干扰。"""
    barrier = threading.Barrier(3)
    errors: list[str] = []

    def worker(idx: int):
        try:
            ctx = AppContext(db_path)          # 独立连接 = 独立客户端
            ctx.current_user = {"id": 1, "username": f"eng{idx}", "role": "工程师"}
            card = ctx.cards_repo.get_by_name(f"RR-{idx}")
            barrier.wait()                     # 三人同时开写
            for k in range(N_WRITES):
                ctx.cards.add_update(
                    card_id=card["id"], update_date=f"2026-09-{(k % 12) + 1:02d}",
                    cum_touches=(k + 1) * 10_000, needle_len=30.0 - k * 0.1,
                    operator=f"eng{idx}",
                )
        except Exception as e:  # noqa: BLE001
            errors.append(f"worker{idx}: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发写入出现未恢复的异常: {errors}"
    ctx = AppContext(db_path)
    total = ctx.db.query_one("SELECT COUNT(*) AS n FROM card_updates")["n"]
    assert total == 3 * N_WRITES, f"数据点总数不符：{total} != {3 * N_WRITES}"
    for i in range(3):
        card = ctx.cards_repo.get_by_name(f"RR-{i}")
        updates = ctx.cards_repo.updates_for_card(card["id"])
        assert len(updates) == N_WRITES
        # 每张卡只含自己操作人的写入，无交叉污染
        assert all(u["operator"] == f"eng{i}" for u in updates)
    # 并发后预测体系仍正常
    preds = ctx.prediction.predict_all()
    assert len(preds) == 3
    assert all(p.points_count == N_WRITES for p in preds)


def test_concurrent_writes_same_card(db_path):
    """最坏情况：三人同时写同一张卡（同一产品的多张卡也会被同一人更新）——不丢不坏。"""
    barrier = threading.Barrier(3)
    errors: list[str] = []

    def worker(idx: int):
        try:
            ctx = AppContext(db_path)
            ctx.current_user = {"id": 1, "username": f"eng{idx}", "role": "工程师"}
            card = ctx.cards_repo.get_by_name("RR-0")
            barrier.wait()
            for k in range(N_WRITES):
                ctx.cards.add_update(
                    card_id=card["id"], update_date="2026-09-12",
                    cum_touches=(idx * N_WRITES + k + 1) * 10_000,
                    needle_len=29.5, operator=f"eng{idx}",
                )
        except Exception as e:  # noqa: BLE001
            errors.append(f"worker{idx}: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    ctx = AppContext(db_path)
    card = ctx.cards_repo.get_by_name("RR-0")
    updates = ctx.cards_repo.updates_for_card(card["id"])
    assert len(updates) == 3 * N_WRITES
    # 每个操作人的写入数量正确（无丢失）
    for i in range(3):
        mine = [u for u in updates if u["operator"] == f"eng{i}"]
        assert len(mine) == N_WRITES


def test_concurrent_mixed_operations(db_path):
    """并发混合：数据点写入 + 状态流转 + 设置修改同时进行，最终一致。"""
    barrier = threading.Barrier(3)
    errors: list[str] = []

    def writer():
        try:
            ctx = AppContext(db_path)
            ctx.current_user = {"id": 1, "username": "w", "role": "工程师"}
            card = ctx.cards_repo.get_by_name("RR-1")
            barrier.wait()
            for k in range(N_WRITES):
                ctx.cards.add_update(card_id=card["id"], update_date="2026-09-12",
                                     cum_touches=(k + 1) * 1000, needle_len=29.8, operator="w")
        except Exception as e:  # noqa: BLE001
            errors.append(f"writer: {e}")

    def mover():
        try:
            ctx = AppContext(db_path)
            ctx.current_user = {"id": 1, "username": "m", "role": "工程师"}
            c0 = ctx.cards_repo.get_by_name("RR-0")
            c2 = ctx.cards_repo.get_by_name("RR-2")
            barrier.wait()
            for k in range(10):
                ctx.warehouse.take_to_machine("m", c0["id"])
                ctx.warehouse.return_to_stock("m", c0["id"])
                ctx.warehouse.scrap("m", c2["id"]) if k == 9 else None
        except Exception as e:  # noqa: BLE001
            errors.append(f"mover: {e}")

    def setter():
        try:
            ctx = AppContext(db_path)
            ctx.current_user = {"id": 1, "username": "s", "role": "管理员"}
            barrier.wait()
            for k in range(10):
                ctx.settings_repo.set("scrap_remind_days", str(10 + k), "s")
        except Exception as e:  # noqa: BLE001
            errors.append(f"setter: {e}")

    threads = [threading.Thread(target=writer), threading.Thread(target=mover),
               threading.Thread(target=setter)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    ctx = AppContext(db_path)
    card = ctx.cards_repo.get_by_name("RR-1")
    assert len(ctx.cards_repo.updates_for_card(card["id"])) == N_WRITES
    assert ctx.cards_repo.get_by_name("RR-0")["status"] == "在库"
    assert ctx.cards_repo.get_by_name("RR-2")["status"] == "报废"
    assert 10 <= ctx.settings_repo.get_int("scrap_remind_days") <= 19
