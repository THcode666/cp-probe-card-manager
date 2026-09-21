"""报表导出页 + 报表导入（自动识别导出格式回灌系统）。"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.app_context import AppContext
from app.services.report_service import ReportService
from app.ui.widgets.common import error_box, info_box


class ReportsPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.report = ReportService(ctx)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("导出 Excel 报表（保存到数据库所在目录的 exports 文件夹）；"
                       "也可把之前导出的报表导回系统，自动识别格式、批量补录针卡与数据点。")
        title.setObjectName("tipLabel")
        title.setWordWrap(True)
        root.addWidget(title)

        import_bar = QHBoxLayout()
        btn_import = QPushButton("导入报表数据（选择导出的 Excel）")
        btn_import.clicked.connect(self._do_import)
        import_bar.addWidget(btn_import)
        import_bar.addStretch()
        root.addLayout(import_bar)

        defs = [
            ("针卡台账", "全部针卡、支持产品、状态、最新测试量与针长", self.report.export_cards),
            ("寿命预测", "每张卡的预测报废测试量、剩余寿命、达成率、预计报废日期", self.report.export_predictions),
            ("需求预估", "各产品到达片数、测试量需求、可用卡与需求张数", self.report.export_demand),
            ("采购建议与采购单", "补卡建议明细 + 全部采购单", self.report.export_purchase),
        ]
        self._paths: dict[str, str] = {}
        for name, desc, fn in defs:
            box = QGroupBox(name)
            lay = QHBoxLayout(box)
            d = QLabel(desc)
            d.setStyleSheet("color:#5F6B7A; font-weight:normal;")
            btn = QPushButton("导出")
            btn.clicked.connect(lambda _=False, f=fn, n=name: self._do(f, n))
            open_btn = QPushButton("打开文件夹")
            open_btn.setObjectName("secondaryBtn")
            open_btn.clicked.connect(self._open_dir)
            lay.addWidget(d, 1)
            lay.addWidget(btn)
            lay.addWidget(open_btn)
            root.addWidget(box)
        root.addStretch()

    def _do(self, fn, name):
        try:
            path = fn()
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self._paths[name] = path
        info_box(self, "导出成功", f"{name} 已导出：\n{path}")

    def _do_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要导入的报表", "", "Excel 报表 (*.xlsx)"
        )
        if not path:
            return
        try:
            stats = self.report.import_from_excel(path, self.ctx.operator)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        lines = [
            f"识别报表类型：{stats['report_type']}",
            f"自动创建产品：{stats['products_created']} 个（参数待在【产品配置】补全）",
            f"新建针卡：{stats['cards_created']} 张",
            f"已存在跳过：{stats['cards_skipped']} 张",
            f"补录数据点：{stats['updates_added']} 条（相同数据自动跳过 {stats['updates_skipped']} 条）",
        ]
        if stats["errors"]:
            lines.append("")
            lines.append(f"失败 {len(stats['errors'])} 行：")
            lines.extend("· " + e for e in stats["errors"][:8])
            if len(stats["errors"]) > 8:
                lines.append(f"……其余 {len(stats['errors']) - 8} 行失败，详见操作日志")
        info_box(self, "导入完成（已记入操作日志）", "\n".join(lines))

    def _open_dir(self):
        base = os.path.dirname(self.ctx.db.db_path)
        path = os.path.join(base, "exports")
        os.makedirs(path, exist_ok=True)
        os.startfile(path)  # noqa: S606

    def refresh(self):
        pass
