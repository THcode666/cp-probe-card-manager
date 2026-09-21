"""业务逻辑自动化测试（不含界面）。

覆盖：建库初始化、认证、针卡 CRUD 校验、数据更新校验、寿命预测数学正确性、
需求预估、采购预警、仓库流转、报表导出。

运行：python -m pytest tests -v
"""

from __future__ import annotations

import datetime as _dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.constants import AlertLevel  # noqa: E402
from app.services.app_context import AppContext  # noqa: E402


@pytest.fixture()
def ctx(tmp_path):
    return AppContext(str(tmp_path / "test.db"))


def _mk_product(ctx, name="0787", tpw=17146, initial=30.0, rated=4_800_000, lead=30):
    return ctx.products_repo.create(
        {"name": name, "touches_per_wafer": tpw, "wph": 60, "initial_len_um": initial,
         "rated_touches": rated, "lead_time_days": lead, "note": ""}
    )


def _mk_card(ctx, name, pids, status="在库", rated=0):
    return ctx.cards.create_card(operator="tester", name=name, product_ids=pids,
                                 status=status, rated_touches=rated)


def _add(ctx, card_id, date, touches, length):
    return ctx.cards.add_update(card_id=card_id, update_date=date, cum_touches=touches,
                                needle_len=length, operator="tester")


# ================= 基础 =================

def test_db_init_and_default_admin(ctx):
    assert ctx.settings_repo.get("scrap_needle_len_um") == "22"
    # 内置管理员可直接登录（演示默认密码，首次登录后应立即修改）
    admin = ctx.users_repo.get_by_username("admin")
    assert admin is not None and admin["role"] == "管理员"
    assert ctx.auth.login("admin", "Admin@12345")["role"] == "管理员"


def test_login_and_password(ctx):
    user = ctx.auth.login("admin", "Admin@12345")
    assert user["username"] == "admin"
    with pytest.raises(ValueError):
        ctx.auth.login("admin", "wrong")
    ctx.auth.change_password(user["id"], "Admin@12345", "newpass1")
    assert ctx.auth.login("admin", "newpass1")


def test_register_with_activation_code(ctx):
    """自助注册：激活码错误拒绝；正确（固定 change-me-activation）则开通工程师账号。"""
    from app.constants import ACTIVATION_CODE, USER_MODULE_PASSWORD

    assert ACTIVATION_CODE == "change-me-activation"          # 激活码固定，不在系统设置中
    assert USER_MODULE_PASSWORD == "change-me-admin"     # 用户管理门禁密码
    # 激活码不再是系统设置项（老库会被迁移清理）
    assert ctx.settings_repo.get("register_activation_code") is None
    # 激活码错误 → 拒绝且不留痕迹
    with pytest.raises(ValueError, match="激活码"):
        ctx.auth.register("zhangsan", "pass123", "wrong-code")
    assert ctx.users_repo.get_by_username("zhangsan") is None
    # 激活码正确 → 注册成功，默认工程师角色，可直接登录
    uid = ctx.auth.register("zhangsan", "pass123", "change-me-activation")
    assert ctx.users_repo.get(uid)["role"] == "工程师"
    assert ctx.auth.login("zhangsan", "pass123")
    # 重复用户名 → 拒绝
    with pytest.raises(ValueError, match="已存在"):
        ctx.auth.register("zhangsan", "pass123", "change-me-activation")
    ctx.auth.register("lisi", "pass123", "change-me-activation")


def test_admin_view_password(ctx):
    """管理员可查看（注册/新建/重置过的）账号密码明文。"""
    uid = ctx.auth.register("zhangsan", "s3cret99", "change-me-activation")
    assert ctx.auth.reveal_password("admin", uid) == "s3cret99"
    # 重置后查看的是新密码
    ctx.auth.reset_password("admin", uid, "newpass88")
    assert ctx.auth.reveal_password("admin", uid) == "newpass88"
    # 查看动作写审计日志
    logs = ctx.audit_repo.list_recent()
    assert any("查看密码" in l["action"] for l in logs)


def test_admin_delete_user_rules(ctx):
    """删除账号：不能删自己；非管理员删除被拒；管理员可删另一个管理员与普通账号。"""
    admin = ctx.users_repo.get_by_username("admin")
    # 再造一个管理员与一个普通工程师
    ctx.auth.create_user("admin", "admin2", "admin234", "管理员")
    admin2 = ctx.users_repo.get_by_username("admin2")
    uid = ctx.auth.register("wangwu", "pass123", "change-me-activation")
    eng = ctx.users_repo.get(uid)

    # 不能删自己
    with pytest.raises(ValueError, match="自己"):
        ctx.auth.delete_user("admin", admin["id"])
    # 非管理员身份调用删除 → 服务层权限拦截
    with pytest.raises(ValueError, match="管理员"):
        ctx.auth.delete_user("wangwu", admin2["id"])
    # 管理员可删除另一个管理员
    ctx.auth.delete_user("admin", admin2["id"])
    assert ctx.users_repo.get_by_username("admin2") is None
    # 普通工程师可删
    ctx.auth.delete_user("admin", eng["id"])
    assert ctx.users_repo.get_by_username("wangwu") is None


# ================= 针卡 CRUD =================

def test_card_name_unique(ctx):
    pid = _mk_product(ctx)
    _mk_card(ctx, "RR-01", [pid])
    with pytest.raises(ValueError, match="已存在"):
        _mk_card(ctx, "RR-01", [pid])


def test_card_requires_product(ctx):
    with pytest.raises(ValueError, match="产品"):
        _mk_card(ctx, "RR-XX", [])


# ================= 数据更新校验 =================

def test_add_update_warnings(ctx):
    pid = _mk_product(ctx)
    cid = _mk_card(ctx, "RR-01", [pid])
    _add(ctx, cid, "2026-09-01", 1_000_000, 27.3)
    # 累计测试量倒挂 → 软警告（不抛异常）
    warnings = _add(ctx, cid, "2026-09-02", 900_000, 27.0)
    assert any("小于" in w for w in warnings)
    # 针长超过初始针长 5% → 警告
    warnings2 = _add(ctx, cid, "2026-09-03", 1_100_000, 32.0)
    assert any("初始针长" in w for w in warnings2)
    # 针长到报废线 → 警告
    warnings3 = _add(ctx, cid, "2026-09-04", 1_200_000, 21.0)
    assert any("报废" in w for w in warnings3)


# ================= 寿命预测 =================

def _feed_linear_life(ctx, cid, touches0=0):
    """三点精确线性：磨损 8um/300 万次 → 预测报废测试量应为 touches0+300 万。"""
    _add(ctx, cid, "2026-08-01", touches0 + 0, 30.0)
    _add(ctx, cid, "2026-08-11", touches0 + 1_500_000, 26.0)
    _add(ctx, cid, "2026-08-21", touches0 + 3_000_000, 22.0)


def test_prediction_own_fit_math(ctx):
    pid = _mk_product(ctx)
    cid = _mk_card(ctx, "RR-01", [pid])
    _feed_linear_life(ctx, cid)
    pred = ctx.prediction.predict_card(cid)
    assert pred.curve_source == "own"
    assert pred.touches_at_scrap == pytest.approx(3_000_000, rel=1e-3)
    assert pred.remaining_touches == pytest.approx(0, abs=1_000)  # 已在报废线
    assert pred.achievement_pct == pytest.approx(3_000_000 / 4_800_000 * 100, rel=1e-3)
    assert pred.alert_level == AlertLevel.RED  # 62.5% < 80%


def test_prediction_achievement_ok(ctx):
    """磨损到 2M 时针长 24.67um，外推 3M 到线；额定 300 万 → 达成率 100%，正常。"""
    pid = _mk_product(ctx, rated=3_000_000)
    cid = _mk_card(ctx, "RR-02", [pid])
    _add(ctx, cid, "2026-08-01", 0, 30.0)
    _add(ctx, cid, "2026-08-11", 1_000_000, 27.33)
    _add(ctx, cid, "2026-08-21", 2_000_000, 24.67)
    pred = ctx.prediction.predict_card(cid)
    assert pred.achievement_pct == pytest.approx(100.0, rel=1e-2)
    assert pred.remaining_touches == pytest.approx(1_000_000, rel=1e-2)
    assert pred.alert_level == AlertLevel.OK


def test_prediction_product_curve_fallback(ctx):
    """卡自身只有 2 个点 → 借用同产品类型曲线（池含另一张完整卡）。"""
    pid = _mk_product(ctx)
    full = _mk_card(ctx, "RR-FULL", [pid])
    _feed_linear_life(ctx, full)
    weak = _mk_card(ctx, "RR-WEAK", [pid])
    _add(ctx, weak, "2026-09-01", 1_000_000, 27.4)
    pred = ctx.prediction.predict_card(weak)
    assert pred.curve_source == "product"
    assert pred.touches_at_scrap == pytest.approx(3_000_000, rel=5e-2)
    assert pred.remaining_touches == pytest.approx(2_000_000, rel=5e-2)


def test_prediction_no_points(ctx):
    pid = _mk_product(ctx)
    cid = _mk_card(ctx, "RR-EMPTY", [pid])
    pred = ctx.prediction.predict_card(cid)
    assert pred.alert_level == AlertLevel.UNKNOWN
    assert pred.touches_at_scrap is None


def test_prediction_scrap_date_and_rate(ctx):
    pid = _mk_product(ctx)
    cid = _mk_card(ctx, "RR-03", [pid])
    _add(ctx, cid, "2026-09-01", 1_000_000, 27.33)
    _add(ctx, cid, "2026-09-11", 2_000_000, 24.66)
    pred = ctx.prediction.predict_card(cid)
    assert pred.daily_touch_rate == pytest.approx(100_000, rel=1e-2)
    expected = _dt.date.today() + _dt.timedelta(days=round(pred.days_to_scrap))
    assert pred.scrap_date == expected.isoformat()
    # 进入 14 天报废提醒窗口
    assert any(p.card_id == cid for p in ctx.prediction.scrap_remind_cards())


# ================= 需求预估 =================

def test_demand_and_three_card_rule(ctx):
    pid = _mk_product(ctx)
    ctx.planning_repo.create_station("LOT", 3)
    stations = {s["name"]: s["id"] for s in ctx.planning_repo.list_stations()}
    ctx.planning_repo.set_wip(pid, stations["LOT"], 100, "tester")
    cid = _mk_card(ctx, "RR-01", [pid])
    _feed_linear_life(ctx, cid)

    d = ctx.demand.compute_for_product(pid)
    assert d.arrivals_by_day == {3: 100}
    assert d.total_touches == pytest.approx(100 * 17146)
    assert d.stock_cards == 1
    assert d.three_card_gap == 2  # 3 张要求 − 1 张在库
    assert d.cards_needed >= 2


def test_demand_n1_stations_count_only(ctx):
    """N1 站点 WIP 只计数量、不参与到达时间推算；N2 正常推算。"""
    pid = _mk_product(ctx)
    ctx.planning_repo.create_station("前段A", 60, stage="N1")
    ctx.planning_repo.create_station("前段B", 90, stage="N1")
    ctx.planning_repo.create_station("临近CP", 2, stage="N2")
    stations = {s["name"]: s["id"] for s in ctx.planning_repo.list_stations()}
    ctx.planning_repo.set_wip(pid, stations["前段A"], 300, "tester")
    ctx.planning_repo.set_wip(pid, stations["前段B"], 500, "tester")
    ctx.planning_repo.set_wip(pid, stations["临近CP"], 40, "tester")

    d = ctx.demand.compute_for_product(pid)
    # N1 不进到达推算
    assert d.arrivals_by_day == {2: 40}
    assert d.total_wafers == 40
    # N1 只计数量
    assert d.n1_wip_total == 800
    assert d.n1_wip_detail == {"前段A": 300, "前段B": 500}


def test_demand_three_card_counts_instock_only(ctx):
    """三卡规则只数【在库】：在用卡不计入储备。"""
    pid = _mk_product(ctx)
    c1 = _mk_card(ctx, "RR-01", [pid])                      # 在库
    c2 = _mk_card(ctx, "RR-02", [pid], status="在用")        # 在用 → 不计入
    d = ctx.demand.compute_for_product(pid)
    assert d.stock_cards == 1
    assert d.three_card_gap == 2
    # 产能口径（采购缺口用）仍包含在用卡
    assert d.capacity_touches == 0  # 无数据点时余量为 0，但卡数口径已验证


def test_demand_station_far_beyond_horizon_excluded(ctx):
    pid = _mk_product(ctx)
    ctx.planning_repo.create_station("远端", 60)  # 超出 14 天展望
    sid = ctx.planning_repo.list_stations()[0]["id"]
    ctx.planning_repo.set_wip(pid, sid, 500, "tester")
    d = ctx.demand.compute_for_product(pid)
    assert d.total_wafers == 0


# ================= 采购预警 =================

def test_purchase_urgency_and_qty(ctx):
    pid = _mk_product(ctx, lead=30)  # 提前期 30 天 + 缓冲 7 天
    ctx.planning_repo.create_station("LOT", 1)
    ctx.planning_repo.create_station("FT", 3)
    stations = {s["name"]: s["id"] for s in ctx.planning_repo.list_stations()}
    ctx.planning_repo.set_wip(pid, stations["LOT"], 100, "tester")
    ctx.planning_repo.set_wip(pid, stations["FT"], 100, "tester")
    # 总需求 ≈ 3.43M；两张卡各余约 1M/2M（合计 3M）→ 第 3 天出现缺口
    c1 = _mk_card(ctx, "RR-01", [pid])
    _add(ctx, c1, "2026-08-01", 0, 30.0)
    _add(ctx, c1, "2026-08-21", 2_000_000, 24.67)
    c2 = _mk_card(ctx, "RR-02", [pid])
    _add(ctx, c2, "2026-08-01", 0, 30.0)
    _add(ctx, c2, "2026-08-21", 1_000_000, 27.33)

    a = ctx.purchase.advise_for_product(pid)
    assert a.shortage_day is not None and a.shortage_day <= 5
    assert a.urgency == AlertLevel.RED  # 缺口日 3 − 提前期 30 − 缓冲 7 < 0
    assert a.suggested_qty >= 1 + a.three_card_gap  # 测试量缺口折算 + 三卡缺口

    # 登记在途采购单后建议数量应扣减
    ctx.purchases_repo.create(pid, 5, "2026-09-12", "2026-10-12", "tester")
    a2 = ctx.purchase.advise_for_product(pid)
    assert a2.in_transit == 5
    assert a2.suggested_qty == max(0, a.suggested_qty - 5)


def test_purchase_no_shortage_when_capacity_large(ctx):
    pid = _mk_product(ctx, lead=30)
    cid = _mk_card(ctx, "RR-01", [pid])
    _feed_linear_life(ctx, cid)  # 剩余≈0... 直接造一张余量大的卡
    c2 = _mk_card(ctx, "RR-02", [pid])
    _add(ctx, c2, "2026-09-01", 0, 30.0)
    _add(ctx, c2, "2026-09-11", 100_000, 29.0)
    d = ctx.demand.compute_for_product(pid)
    assert d.total_touches == 0  # 无 WIP → 无需求
    a = ctx.purchase.advise_for_product(pid)
    assert a.shortage_day is None


# ================= 仓库流转 =================

def test_warehouse_transitions(ctx):
    pid = _mk_product(ctx)
    cid = _mk_card(ctx, "RR-01", [pid])
    ctx.warehouse.take_to_machine("tester", cid)
    assert ctx.cards_repo.get(cid)["status"] == "在用"
    ctx.warehouse.return_to_stock("tester", cid)
    assert ctx.cards_repo.get(cid)["status"] == "在库"
    # 非法流转被拒绝
    with pytest.raises(ValueError):
        ctx.warehouse.return_to_stock("tester", cid)  # 在库不能"下机"
    ctx.warehouse.scrap("tester", cid)
    assert ctx.cards_repo.get(cid)["status"] == "报废"
    assert ctx.cards_repo.get(cid)["scrapped_date"] is not None
    # 报废卡不计入在库
    d = ctx.demand.compute_for_product(pid)
    assert d.stock_cards == 0 and d.three_card_gap == 3


def test_scrap_card_keeps_data_for_pool(ctx):
    pid = _mk_product(ctx)
    cid = _mk_card(ctx, "RR-OLD", [pid])
    _feed_linear_life(ctx, cid)
    ctx.warehouse.scrap("tester", cid)
    pts = ctx.cards_repo.update_points_for_product(pid)
    assert len(pts) == 3  # 报废卡数据仍参与类型曲线拟合


# ================= 设置与报表 =================

def test_setting_change_affects_prediction(ctx):
    pid = _mk_product(ctx)
    cid = _mk_card(ctx, "RR-01", [pid])
    _feed_linear_life(ctx, cid)
    ctx.settings_repo.set("rated_touches_default", "3000000", "tester")
    assert ctx.prediction.default_rated == 3_000_000


def test_excel_exports(ctx, tmp_path):
    pid = _mk_product(ctx)
    cid = _mk_card(ctx, "RR-01", [pid])
    _add(ctx, cid, "2026-09-01", 1_000_000, 27.3)
    ctx.planning_repo.create_station("LOT", 3)
    from app.services.report_service import ReportService
    rs = ReportService(ctx)
    for fn in (rs.export_cards, rs.export_predictions, rs.export_demand, rs.export_purchase):
        path = fn()
        assert os.path.exists(path) and os.path.getsize(path) > 0


def test_audit_log_written(ctx):
    pid = _mk_product(ctx)
    _mk_card(ctx, "RR-01", [pid])
    logs = ctx.audit_repo.list_recent()
    assert any("新卡入库" in l["action"] for l in logs)
