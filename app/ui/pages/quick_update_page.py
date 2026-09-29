"""数据更新页：第一步选择针卡 → 第二步录入数据；下方最近记录支持删除误录数据。"""

from __future__ import annotations

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.app_context import AppContext
from app.ui.widgets.common import confirm_box, error_box, fill_table, make_table, show_warnings


class QuickUpdatePage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)

        left_box = QGroupBox("第一步：选择针卡")
        llay = QVBoxLayout(left_box)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索针卡名…")
        # 250ms 防抖：卡数多时逐键全量过滤会卡输入，停顿后一次性过滤
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._fill_card_list)
        self.search_edit.textChanged.connect(self._search_timer.start)
        self.card_combo = QComboBox()
        llay.addWidget(self.search_edit)
        llay.addWidget(self.card_combo, 1)
        self.card_combo.currentIndexChanged.connect(self._on_card_changed)

        right_box = QGroupBox("第二步：录入本次数据")
        form = QFormLayout(right_box)
        form.setSpacing(10)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.touches_spin = QDoubleSpinBox()
        self.touches_spin.setRange(0, 1e9)
        self.touches_spin.setDecimals(0)
        self.touches_spin.setGroupSeparatorShown(True)
        self.len_spin = QDoubleSpinBox()
        self.len_spin.setRange(0, 1000)
        self.len_spin.setDecimals(1)
        self.len_spin.setSuffix(" um")
        self.len_spin.setSingleStep(0.5)
        self.note_edit = QLineEdit()
        form.addRow("数据日期：", self.date_edit)
        form.addRow("累计测试量（自新卡起）：", self.touches_spin)
        form.addRow("当前针长：", self.len_spin)
        form.addRow("备注：", self.note_edit)
        btn = QPushButton("保存本条记录")
        btn.clicked.connect(self._save)
        form.addRow(btn)
        self.hint_label = QLabel("")
        self.hint_label.setObjectName("tipLabel")
        form.addRow(self.hint_label)

        top.addWidget(left_box, 1)
        top.addWidget(right_box, 1)
        root.addLayout(top, 2)

        recent_box = QGroupBox("最近录入记录（选中一条后可删除误录数据）")
        rlay = QVBoxLayout(recent_box)
        bar = QHBoxLayout()
        btn_del = QPushButton("删除选中的记录")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_selected)
        bar.addWidget(btn_del)
        bar.addStretch()
        rlay.addLayout(bar)
        self.recent_table = make_table(["ID", "日期", "针卡", "累计测试量", "针长(um)", "操作人", "备注"])
        self.recent_table.setColumnWidth(0, 50)
        self.recent_table.setColumnHidden(0, True)  # ID 隐藏列，用于定位删除
        rlay.addWidget(self.recent_table)
        root.addWidget(recent_box, 1)

        self._fill_card_list()
        self._refresh_recent()

    def _fill_card_list(self):
        kw = self.search_edit.text().strip()
        self.card_combo.blockSignals(True)
        self.card_combo.clear()
        rows = self.ctx.cards_repo.list_cards(keyword=kw or None)
        for r in rows:
            if r["status"] != "报废":
                label = f"{r['name']}　[{r['status']}]　{r['product_names'] or ''}"
                self.card_combo.addItem(label, r["id"])
        self.card_combo.blockSignals(False)
        self._on_card_changed()

    def _on_card_changed(self):
        cid = self.card_combo.currentData()
        self.hint_label.setText("")
        if not cid:
            self.touches_spin.setValue(0)
            self.len_spin.setValue(0)
            return
        latest = self.ctx.cards_repo.latest_update(cid)
        if latest:
            self.touches_spin.setValue(latest["cum_touches"])
            self.len_spin.setValue(latest["needle_len"])
            self.hint_label.setText(
                f"最近记录：{latest['update_date']}　累计 {latest['cum_touches']:,.0f} 次　针长 {latest['needle_len']:g}um"
                "（在最近值基础上累加/修改）"
            )
        else:
            self.touches_spin.setValue(0)
            self.len_spin.setValue(0)
            self.hint_label.setText("该卡还没有数据点，请录入首个数据点")

    def _save(self):
        cid = self.card_combo.currentData()
        if not cid:
            error_box(self, "请先选择针卡")
            return
        try:
            warnings = self.ctx.cards.add_update(
                operator=self.ctx.operator,
                card_id=cid,
                update_date=self.date_edit.date().toString("yyyy-MM-dd"),
                cum_touches=self.touches_spin.value(),
                needle_len=self.len_spin.value(),
                note=self.note_edit.text(),
            )
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.note_edit.clear()
        self._on_card_changed()
        self._refresh_recent()
        show_warnings(self, warnings)

    # ---------- 删除误录记录 ----------

    def _selected_record(self):
        idx = self.recent_table.currentRow()
        if idx < 0:
            error_box(self, "请先在下方列表中选中一条记录")
            return None
        item = self.recent_table.item(idx, 0)
        card_name = self.recent_table.item(idx, 2).text()
        return int(item.text()), card_name

    def _delete_selected(self):
        sel = self._selected_record()
        if not sel:
            return
        update_id, card_name = sel
        if not confirm_box(
            self, "确认删除",
            f"确定删除【{card_name}】的一条更新记录吗？\n删除后该卡的磨损曲线与预测将按剩余记录重新计算。",
        ):
            return
        try:
            self.ctx.cards.delete_update(self.ctx.operator, update_id, card_name)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self._refresh_recent()
        self._on_card_changed()

    def _refresh_recent(self):
        rows = self.ctx.db.query(
            "SELECT cu.id, cu.update_date, c.name, cu.cum_touches, cu.needle_len, cu.operator, cu.note "
            "FROM card_updates cu JOIN cards c ON c.id = cu.card_id "
            "ORDER BY cu.id DESC LIMIT 100"
        )
        fill_table(
            self.recent_table,
            [[r["id"], r["update_date"], r["name"], r["cum_touches"], r["needle_len"], r["operator"], r["note"]]
             for r in rows],
            align_center_cols={0, 1, 2, 3, 4, 5},
        )

    def refresh(self):
        self._fill_card_list()
        self._refresh_recent()
