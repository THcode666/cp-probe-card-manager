"""操作日志页（仅管理员）。"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from app.services.app_context import AppContext
from app.ui.widgets.common import fill_table, make_table


class AuditPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        bar = QHBoxLayout()
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
        rows = self.ctx.audit_repo.list_recent(limit=500, keyword=self.keyword_edit.text().strip() or None)
        fill_table(
            self.table,
            [[r["ts"], r["operator"], r["module"], r["action"], r["detail"]] for r in rows],
        )
