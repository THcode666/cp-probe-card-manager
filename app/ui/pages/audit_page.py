"""操作日志页（仅管理员）：全量审计日志，支持按模块筛选与关键字搜索。"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from app.services.app_context import AppContext
from app.ui.widgets.common import fill_table, make_table


class AuditPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("模块："))
        self.module_combo = QComboBox()
        self.module_combo.setMinimumContentsLength(12)
        self.module_combo.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.module_combo)
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("按操作人 / 模块 / 动作 / 详情搜索…")
        self.keyword_edit.returnPressed.connect(self.refresh)
        btn = QPushButton("查询")
        btn.clicked.connect(self.refresh)
        bar.addWidget(self.keyword_edit, 1)
        bar.addWidget(btn)
        root.addLayout(bar)
        self.table = make_table(["时间", "操作人", "模块", "动作", "详情"])
        root.addWidget(self.table, 1)

    def refresh(self):
        # 筛选下拉始终含"全部模块 + 库中出现过的模块"，密码类操作（用户管理模块）
        # 即使被日常数据更新刷出最近窗口，选对应模块也能直接查到
        current = self.module_combo.currentData()
        modules = ["全部模块"] + self.ctx.audit_repo.list_modules()
        self.module_combo.blockSignals(True)
        self.module_combo.clear()
        self.module_combo.addItem("全部模块", None)
        for m in modules[1:]:
            self.module_combo.addItem(m, m)
        if current:
            idx = self.module_combo.findData(current)
            if idx >= 0:
                self.module_combo.setCurrentIndex(idx)
        self.module_combo.blockSignals(False)

        rows = self.ctx.audit_repo.list_recent(
            limit=1000,
            keyword=self.keyword_edit.text().strip() or None,
            module=self.module_combo.currentData(),
        )
        fill_table(
            self.table,
            [[r["ts"], r["operator"], r["module"], r["action"], r["detail"]] for r in rows],
        )
