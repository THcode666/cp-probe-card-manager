"""系统设置页：所有全局业务参数（全部可改，存数据库）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.app_context import AppContext
from app.ui.widgets.common import error_box, fill_table, make_table

SETTING_LABELS = {
    "scrap_needle_len_um": "针长报废线（um）——低于该针长不可继续测试",
    "rated_touches_default": "默认针卡最大测试量（次）——产品未单独配置时的兜底值",
    "warn_yellow_pct": "寿命达成率黄色预警阈值（%）",
    "warn_red_pct": "寿命达成率红色预警阈值（%）",
    "scrap_remind_days": "预计报废提前提醒天数（天）",
    "purchase_buffer_days": "采购缓冲天数（提前期 + 缓冲 = 最晚下单日）",
    "min_cards_per_product": "每个产品最少在库针卡数（三卡规则，只数在库）",
    "demand_horizon_days": "需求预测展望天数（天）",
    "min_points_for_own_fit": "单卡自有拟合曲线所需最少数据点数",
    "backup_keep_days": "数据库自动备份保留天数（天）",
    "default_wph": "新产品默认 WPH（片/小时·台）",
}


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        tip = QLabel(
            "以下全局参数均可修改并立即生效；产品级参数（片耗、WPH、初始针长、针卡最大测试量、提前期）"
            "请在【产品配置】页修改。"
        )
        tip.setObjectName("tipLabel")
        root.addWidget(tip)

        bar = QHBoxLayout()
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("在此输入选中参数的新值…")
        btn_set = QPushButton("修改选中参数")
        btn_set.clicked.connect(self._apply)
        bar.addWidget(self.value_edit, 1)
        bar.addWidget(btn_set)
        root.addLayout(bar)

        self.table = make_table(["参数", "当前值", "说明"])
        self.table.doubleClicked.connect(self._edit_inline)
        root.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        data = self.ctx.settings_repo.all()
        rows = []
        for key in sorted(data):
            if key not in SETTING_LABELS:
                continue  # 隐藏已废弃/内部参数
            rows.append([key, data[key]["value"], SETTING_LABELS.get(key, "")])
        fill_table(self.table, rows, align_center_cols={1})

    def _selected_key(self) -> str | None:
        idx = self.table.currentRow()
        if idx < 0:
            error_box(self, "请先选择参数")
            return None
        return self.table.item(idx, 0).text()

    def _edit_inline(self):
        idx = self.table.currentRow()
        if idx < 0:
            return
        self.value_edit.setText(self.table.item(idx, 1).text())
        self.value_edit.setFocus()

    def _apply(self):
        key = self._selected_key()
        if not key:
            return
        new_value = self.value_edit.text().strip()
        try:
            self.ctx.settings_repo.set(key, new_value, self.ctx.operator)
        except ValueError as e:
            error_box(self, e)
            return
        self.ctx.audit_repo.log(self.ctx.operator, "系统设置", "修改参数", f"{key} → {new_value}")
        self.refresh()
        QMessageBox.information(self, "完成", f"参数 {key} 已改为 {new_value}")
