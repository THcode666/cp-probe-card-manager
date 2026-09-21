"""报表导入回归测试：导出 → 空库导入 → 校验自动识别与数据完整性。"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.app_context import AppContext  # noqa: E402
from app.services.report_service import ReportService  # noqa: E402


def _mk_product(ctx, name="0787"):
    return ctx.products_repo.create({"name": name, "touches_per_wafer": 17146, "wph": 60,
                                     "initial_len_um": 30.0, "rated_touches": 4800000,
                                     "lead_time_days": 30, "note": ""})


def test_import_cards_report_roundtrip(tmp_path):
    """针卡台账报表 → 新系统导入：产品/针卡/数据点自动重建。"""
    src = AppContext(str(tmp_path / "src.db"))
    src.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    pid = _mk_product(src)
    src.cards.create_card("admin", "RR-01", [pid], note="测试卡")
    src.cards.add_update(card_id=src.cards_repo.get_by_name("RR-01")["id"],
                         update_date="2026-09-01", cum_touches=1_800_000,
                         needle_len=25.4, operator="admin")
    path = ReportService(src).export_cards()

    dst = AppContext(str(tmp_path / "dst.db"))  # 全新的空库
    dst.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    stats = ReportService(dst).import_from_excel(path, "admin")

    assert stats["report_type"] == "针卡台账"
    assert stats["products_created"] == 1
    assert stats["cards_created"] == 1
    assert stats["cards_skipped"] == 0
    assert stats["updates_added"] == 1
    assert stats["errors"] == []

    card = dst.cards_repo.get_by_name("RR-01")
    assert card is not None and card["note"] == "测试卡"
    assert dst.cards_repo.product_ids_of_card(card["id"]) == [
        dst.products_repo.get_by_name("0787")["id"]]
    u = dst.cards_repo.latest_update(card["id"])
    assert u["cum_touches"] == 1_800_000 and u["needle_len"] == 25.4
    assert u["update_date"] == "2026-09-01"


def test_import_predictions_report_roundtrip(tmp_path):
    """寿命预测报表（含注释行偏移）→ 空库导入：自动识别格式。"""
    src = AppContext(str(tmp_path / "src2.db"))
    src.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    pid = _mk_product(src, "0855")
    cid = src.cards.create_card("admin", "RR-02", [pid])
    src.cards.add_update(card_id=cid, update_date="2026-09-10", cum_touches=2_400_000,
                         needle_len=23.8, operator="admin")
    path = ReportService(src).export_predictions()

    dst = AppContext(str(tmp_path / "dst2.db"))
    dst.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    stats = ReportService(dst).import_from_excel(path, "admin")

    assert stats["report_type"] == "寿命预测"
    assert stats["cards_created"] == 1 and stats["updates_added"] == 1
    card = dst.cards_repo.get_by_name("RR-02")
    assert card is not None
    assert dst.cards_repo.latest_update(card["id"])["cum_touches"] == 2_400_000


def test_import_skips_existing_and_dedupes(tmp_path):
    """重复导入：已存在的卡跳过、相同数据点不重复入库（幂等）。"""
    src = AppContext(str(tmp_path / "src3.db"))
    src.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    pid = _mk_product(src)
    src.cards.create_card("admin", "RR-01", [pid])
    src.cards.add_update(card_id=src.cards_repo.get_by_name("RR-01")["id"],
                         update_date="2026-09-01", cum_touches=100_000,
                         needle_len=29.0, operator="admin")
    path = ReportService(src).export_cards()

    dst = AppContext(str(tmp_path / "dst3.db"))
    dst.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    first = ReportService(dst).import_from_excel(path, "admin")
    second = ReportService(dst).import_from_excel(path, "admin")

    assert first["cards_created"] == 1 and first["updates_added"] == 1
    assert second["cards_skipped"] == 1          # 卡已存在
    assert second["updates_added"] == 0          # 相同数据点去重
    assert second["updates_skipped"] == 1


def test_import_unrecognized_file_rejected(tmp_path):
    """非本系统导出的 Excel → 明确报错，不产生脏数据。"""
    from openpyxl import Workbook
    bogus = str(tmp_path / "bogus.xlsx")
    wb = Workbook()
    wb.active.append(["随便", "一个", "表"])
    wb.active.append([1, 2, 3])
    wb.save(bogus)

    dst = AppContext(str(tmp_path / "dst4.db"))
    dst.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    with pytest.raises(ValueError, match="无法识别"):
        ReportService(dst).import_from_excel(bogus, "admin")


def test_import_captures_row_errors(tmp_path):
    """个别行数据坏（缺产品、测试量非数字）→ 不中断整体导入，逐行报告。"""
    from openpyxl import Workbook
    bad = str(tmp_path / "bad.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["针卡名称", "支持产品", "状态", "当前累计测试量", "当前针长(um)", "最近更新日期", "入库日期", "备注"])
    ws.append(["RR-GOOD", "0787", "在库", 1_000_000, 27.5, "2026-09-01", "2026-08-01", ""])
    ws.append(["RR-BAD1", "", "在库", 1_000_000, 27.5, "2026-09-01", "2026-08-01", ""])   # 无产品
    ws.append(["RR-BAD2", "0787", "在库", "abc", 27.5, "2026-09-01", "2026-08-01", ""])   # 测试量非数字
    wb.save(bad)

    dst = AppContext(str(tmp_path / "dst5.db"))
    dst.current_user = {"id": 1, "username": "admin", "role": "管理员"}
    stats = ReportService(dst).import_from_excel(bad, "admin")
    assert stats["cards_created"] == 1
    assert len(stats["errors"]) == 2
    assert dst.cards_repo.get_by_name("RR-GOOD") is not None
    assert dst.cards_repo.get_by_name("RR-BAD1") is None
