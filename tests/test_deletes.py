"""删除功能回归：删除站点（级联 WIP）、删除产品（采购单/孤儿卡阻断）、删除采购单。"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.app_context import AppContext  # noqa: E402


@pytest.fixture()
def ctx(tmp_path):
    c = AppContext(str(tmp_path / "del.db"))
    c.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    return c


def _mk_product(ctx, name="0787"):
    return ctx.products_repo.create({"name": name, "touches_per_wafer": 17146, "wph": 60,
                                     "initial_len_um": 30.0, "rated_touches": 4800000,
                                     "lead_time_days": 30, "note": ""})


def test_delete_station_cascades_wip(ctx):
    sid = ctx.planning_repo.create_station("LOT", 3)
    pid = _mk_product(ctx)
    ctx.planning_repo.set_wip(pid, sid, 120, "admin")
    ctx.planning_repo.delete_station(sid)
    assert ctx.planning_repo.get_station(sid) is None
    assert all(w["station_id"] != sid for w in ctx.planning_repo.list_wip())  # WIP 级联删除


def test_delete_product_blocks_on_purchase(ctx):
    pid = _mk_product(ctx)
    ctx.purchases_repo.create(pid, 2, "2026-09-12", "2026-10-12", "admin")
    assert ctx.products_repo.purchase_count(pid) == 1
    with pytest.raises(ValueError, match="采购单"):
        ctx.products_repo.delete(pid)      # 数据层强制阻断
    assert ctx.products_repo.get(pid) is not None


def test_delete_product_blocks_orphan_cards(ctx):
    pid = _mk_product(ctx)
    ctx.cards.create_card("admin", "RR-ONLY", [pid])   # 仅支持该产品
    assert [r["name"] for r in ctx.products_repo.orphan_cards(pid)] == ["RR-ONLY"]
    # 双产品卡不受影响
    pid2 = _mk_product(ctx, "0855")
    ctx.cards.create_card("admin", "RR-DUAL", [pid, pid2])
    assert "RR-DUAL" not in [r["name"] for r in ctx.products_repo.orphan_cards(pid)]


def test_delete_product_success(ctx):
    pid = _mk_product(ctx)
    sid = ctx.planning_repo.create_station("LOT", 3)
    ctx.planning_repo.set_wip(pid, sid, 50, "admin")
    ctx.cards.create_card("admin", "RR-DUAL", [pid])
    _mk_product(ctx, "0855")
    dual = ctx.cards_repo.get_by_name("RR-DUAL")
    ctx.cards.update_card("admin", dual["id"], "RR-DUAL",
                          [pid, ctx.products_repo.get_by_name("0855")["id"]])

    ctx.products_repo.delete(pid)
    assert ctx.products_repo.get(pid) is None
    assert ctx.planning_repo.list_wip(pid) == []          # WIP 级联删除
    assert pid not in ctx.cards_repo.product_ids_of_card(dual["id"])  # 关联解除
    assert ctx.cards_repo.get_by_name("RR-DUAL") is not None         # 卡本体保留


def test_delete_purchase_order_reduces_in_transit(ctx):
    pid = _mk_product(ctx)
    po_id = ctx.purchases_repo.create(pid, 5, "2026-09-12", "2026-10-12", "admin")
    assert ctx.purchases_repo.in_transit_qty(pid) == 5
    ctx.purchases_repo.delete(po_id)
    assert ctx.purchases_repo.in_transit_qty(pid) == 0
    assert ctx.purchases_repo.list_all() == []
