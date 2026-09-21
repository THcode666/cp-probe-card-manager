"""GUI 冒烟测试：离屏实例化全部页面与对话框，验证界面代码与业务层集成无异常。

运行：python -m pytest tests/test_gui_smoke.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# 测试环境没有事件循环，模态弹窗会永久阻塞：让所有弹窗自动返回"No"，
# 但把弹窗文本打印出来，避免真实异常（如属性错误）被静默吞掉。
def _auto_reply_factory():
    import sys

    def reply(*args, **kwargs):
        for a in args:
            if isinstance(a, str):
                print("[MODAL]", a, file=sys.stderr)
        texts = [str(v) for v in kwargs.values()]
        if texts:
            print("[MODAL]", *texts, file=sys.stderr)
        return QMessageBox.StandardButton.No
    return reply


auto_no = _auto_reply_factory()
QMessageBox.critical = staticmethod(auto_no)
QMessageBox.warning = staticmethod(auto_no)
QMessageBox.information = staticmethod(auto_no)
QMessageBox.question = staticmethod(auto_no)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def seeded_ctx(tmp_path):
    from app.services.app_context import AppContext

    ctx = AppContext(str(tmp_path / "gui.db"))
    ctx.current_user = {"id": 1, "username": "admin", "role": "管理员"}

    p1 = ctx.products_repo.create(
        {"name": "0787", "touches_per_wafer": 17146, "wph": 60, "initial_len_um": 30.0,
         "rated_touches": 4800000, "lead_time_days": 30, "note": ""}
    )
    p2 = ctx.products_repo.create(
        {"name": "0855", "touches_per_wafer": 20000, "wph": 50, "initial_len_um": 30.0,
         "rated_touches": 0, "lead_time_days": 45, "note": ""}
    )
    c1 = ctx.cards.create_card("admin", "RR-01", [p1, p2])
    ctx.cards.add_update(card_id=c1, update_date="2026-09-01", cum_touches=1_000_000,
                         needle_len=27.4, operator="admin")
    ctx.cards.add_update(card_id=c1, update_date="2026-09-10", cum_touches=1_600_000,
                         needle_len=26.5, operator="admin")
    c2 = ctx.cards.create_card("admin", "RR-02", [p1], status="在用")
    ctx.cards.add_update(card_id=c2, update_date="2026-09-05", cum_touches=2_500_000,
                         needle_len=23.8, operator="admin")
    ctx.cards.create_card("admin", "RR-03", [p2], status="报废")
    ctx.planning_repo.create_station("LOT", 3)
    ctx.planning_repo.create_station("FT1", 1)
    for s in ctx.planning_repo.list_stations():
        ctx.planning_repo.set_wip(p1, s["id"], 120, "admin")
    ctx.purchases_repo.create(p1, 2, "2026-09-01", "2026-10-01", "admin")
    yield ctx


def test_all_pages_refresh(qapp, seeded_ctx):
    from app.ui.main_window import MainWindow

    # 用户管理有管理密码门禁：测试中直接放行（密码门禁另由服务测试覆盖常量）
    MainWindow._ask_module_password = lambda self: True
    win = MainWindow(seeded_ctx)
    assert win.nav.item(win.nav.count() - 1).text() == "用户管理"  # 固定在导航最下方
    for i in range(win.nav.count()):
        win.nav.setCurrentRow(i)  # 触发 _switch_page → page.refresh()
    win.close()


def test_users_module_password_gate(qapp, seeded_ctx):
    """门禁：密码错误 → 导航回退、不进入页面；正确 → 进入。"""
    from app.constants import USER_MODULE_PASSWORD
    from app.ui.main_window import MainWindow

    MainWindow._ask_module_password = lambda self: False
    win = MainWindow(seeded_ctx)
    users_row = win.nav.count() - 1
    win._prev_nav_index = 0
    win.nav.setCurrentRow(users_row)
    assert win._users_unlocked is False
    assert win.stack.currentIndex() != users_row   # 被拒后停留在原页面
    win.close()

    MainWindow._ask_module_password = lambda self: True
    win2 = MainWindow(seeded_ctx)
    win2._prev_nav_index = 0
    win2.nav.setCurrentRow(win2.nav.count() - 1)
    assert win2._users_unlocked is True
    assert win2.stack.currentIndex() == win2.nav.count() - 1
    win2.close()
    assert USER_MODULE_PASSWORD == "change-me-admin"


def test_dashboard_values(qapp, seeded_ctx):
    from app.ui.pages.dashboard_page import DashboardPage

    page = DashboardPage(seeded_ctx)
    page.refresh()
    assert page.card_total._value_label.text() == "3"


def test_cards_page_and_dialogs(qapp, seeded_ctx):
    from app.ui.pages.cards_page import CardFormDialog, CardsPage
    from app.ui.pages.card_detail_dialog import CardDetailDialog

    page = CardsPage(seeded_ctx)
    page.refresh()
    assert page.table.rowCount() == 3

    dlg = CardFormDialog(seeded_ctx)  # 新卡入库对话框
    dlg.name_edit.setText("RR-NEW")
    dlg._selected_pids()
    dlg.close()

    row = seeded_ctx.cards_repo.get_by_name("RR-01")
    detail = CardDetailDialog(seeded_ctx, row["id"])  # 详情 + 曲线图
    detail.close()


def test_other_forms(qapp, seeded_ctx):
    from app.ui.pages.products_page import ProductFormDialog
    from app.ui.pages.purchase_page import PurchaseFormDialog
    from app.ui.pages.wip_page import StationFormDialog

    ProductFormDialog(seeded_ctx).close()
    StationFormDialog(seeded_ctx).close()
    PurchaseFormDialog(seeded_ctx).close()


def test_login_dialog(qapp, seeded_ctx):
    from app.ui.login_dialog import LoginDialog

    dlg = LoginDialog(seeded_ctx)
    dlg.user_edit.setText("admin")
    dlg.pwd_edit.setText("Admin@12345")
    dlg._do_login()
    assert dlg.result() == dlg.DialogCode.Accepted


def test_reports_export(qapp, seeded_ctx):
    from app.services.report_service import ReportService

    rs = ReportService(seeded_ctx)
    assert os.path.exists(rs.export_cards())
    assert os.path.exists(rs.export_predictions())
