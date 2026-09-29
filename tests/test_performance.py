"""性能基准测试：大数据量下主控面板级计算不卡顿（弱机优化回归）。

场景：10 个产品 × 每产品 30 张卡 = 300 张卡，每卡 30 个数据点（共 9000 点），
模拟"用了很多年的库"。验证：
① 全量预测批量装载（冷启动）耗时可控（阈值放得很宽，防 CI 抖动）；
② 界面刷新路径（预测→需求→采购建议）热缓存下近似免费；
③ 本进程写操作后缓存自动失效、结果立即反映新数据；
④ 其他客户端提交（PRAGMA data_version 变化）后缓存同样失效。
"""

from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.app_context import AppContext  # noqa: E402


@pytest.fixture(scope="module")
def big_ctx(tmp_path_factory):
    ctx = AppContext(str(tmp_path_factory.mktemp("perf") / "big.db"))
    ctx.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    n_products, n_cards_per, n_points = 10, 30, 30
    for i in range(n_products):
        pid = ctx.products_repo.create(
            {"name": f"P{i:02d}", "touches_per_wafer": 17146, "wph": 60,
             "initial_len_um": 30.0, "rated_touches": 4_800_000, "lead_time_days": 30, "note": ""}
        )
        for j in range(n_cards_per):
            cid = ctx.cards.create_card("admin", f"RR-{i:02d}-{j:02d}", [pid])
            for k in range(n_points):
                ctx.cards.add_update(
                    card_id=cid, update_date=f"2026-{(k % 12) + 1:02d}-15",
                    cum_touches=(k + 1) * 100_000, needle_len=29.0 - k * 0.15,
                    operator="admin",
                )
        ctx.planning_repo.create_station(f"FT{i}", 1 + i)
        ctx.planning_repo.set_wip(pid, ctx.planning_repo.list_stations()[-1]["id"], 100, "admin")
    return ctx


def test_bulk_predict_all_cold_is_bounded(big_ctx):
    """冷启动（第一次全量预测）：批量装载，300 卡 / 9000 点应在宽阈值内完成。"""
    t0 = time.perf_counter()
    preds = big_ctx.prediction.predict_all()
    cold = time.perf_counter() - t0
    assert len(preds) == 300
    assert all(p.points_count == 30 for p in preds)
    assert cold < 15.0, f"全量预测冷启动过慢：{cold:.2f}s"


def test_warm_refresh_is_fast(big_ctx):
    """热缓存（数据未变时的界面刷新路径）：预测+需求+采购建议应接近瞬时。"""
    big_ctx.prediction.predict_all()          # 预热
    big_ctx.demand.compute_all()
    t0 = time.perf_counter()
    big_ctx.prediction.predict_all()
    big_ctx.prediction.scrap_remind_cards()
    big_ctx.demand.compute_all()
    big_ctx.purchase.advise_all()
    warm = time.perf_counter() - t0
    assert warm < 1.0, f"热缓存刷新过慢：{warm:.3f}s"


def test_cache_invalidated_by_local_write(big_ctx):
    """本进程写入新数据点后：缓存失效，预测立即反映新数据。"""
    card = big_ctx.cards_repo.get_by_name("RR-00-00")
    before = big_ctx.prediction.predict_card(card["id"])
    assert before.last_touches == 3_000_000
    big_ctx.cards.add_update(card_id=card["id"], update_date="2026-12-15",
                             cum_touches=3_100_000, needle_len=28.0, operator="admin")
    after = big_ctx.prediction.predict_card(card["id"])
    assert after.last_touches == 3_100_000
    assert after.points_count == 31


def test_cache_invalidated_by_external_commit(big_ctx, tmp_path):
    """其他客户端提交后（data_version 变化）：本进程缓存失效，读到新数据。"""
    other = AppContext(big_ctx.db.db_path)     # 模拟另一台电脑的客户端
    other.current_user = {"id": 1, "username": "eng", "role": "工程师"}
    card = big_ctx.cards_repo.get_by_name("RR-01-00")
    before = big_ctx.prediction.predict_card(card["id"])
    assert before.points_count == 30
    other.cards.add_update(card_id=card["id"], update_date="2026-12-15",
                           cum_touches=3_050_000, needle_len=28.2, operator="eng")
    time.sleep(0.06)  # data_version 有 50ms 记忆窗，等窗口过去后必能感知外部提交
    after = big_ctx.prediction.predict_card(card["id"])
    assert after.points_count == 31, "其他客户端写入后本进程缓存必须失效"
