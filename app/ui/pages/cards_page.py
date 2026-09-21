"""针卡台账页：筛选列表 + 新卡入库 / 编辑 / 详情 / 报废 / 删除。"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QCheckBox,
    QVBoxLayout,
    QWidget,
)

from app.constants import CardStatus
from app.services.app_context import AppContext
from app.ui.pages.card_detail_dialog import CardDetailDialog
from app.ui.widgets.common import (
    alert_badge,
    confirm_box,
    error_box,
    fill_table,
    make_table,
)

LIST_HEADERS = ["针卡名称", "支持产品", "状态", "当前累计测试量", "当前针长(um)", "最近更新",
                "预测报废时测试量", "剩余可测次数", "寿命达成率", "预计报废日期", "预警"]


class CardFormDialog(QDialog):
    """新卡入库 / 编辑针卡。"""

    def __init__(self, ctx: AppContext, card_row=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.card_row = card_row
        self.setWindowTitle("新卡入库" if card_row is None else "编辑针卡")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("针卡名称：", self.name_edit)

        prod_box = QGroupBox("支持的测试产品（可多选）")
        pgrid = QGridLayout(prod_box)
        pgrid.setSpacing(6)
        self.product_checks: list[tuple[int, QCheckBox]] = []
        products = self.ctx.products_repo.list_all()
        for i, p in enumerate(products):
            cb = QCheckBox(p["name"])
            cb.setToolTip(f"片耗 {p['touches_per_wafer']:g} 次/片")
            row, col = divmod(i, 3)
            pgrid.addWidget(cb, row, col)
            self.product_checks.append((p["id"], cb))
        form.addRow(prod_box)

        self.rated_spin = QDoubleSpinBox()
        self.rated_spin.setRange(0, 1e9)
        self.rated_spin.setDecimals(0)
        self.rated_spin.setGroupSeparatorShown(True)
        self.rated_spin.setSpecialValueText("默认（按产品配置）")
        self.rated_spin.setToolTip("仅当这张卡与同产品其他卡寿命不同时才填（如别的卡 480W、这张只到 240W）；\n"
                                   "留 0 表示按产品配置的针卡最大测试量")
        form.addRow("针卡最大测试量覆盖：", self.rated_spin)

        if card_row is None:
            self.date_edit = QDateEdit(QDate.currentDate())
            self.date_edit.setCalendarPopup(True)
            self.date_edit.setDisplayFormat("yyyy-MM-dd")
            form.addRow("入库日期：", self.date_edit)

        self.note_edit = QLineEdit()
        form.addRow("备注：", self.note_edit)
        root.addLayout(form)

        # 新卡可同时录入首个数据点
        self.init_box: QGroupBox | None = None
        if card_row is None:
            self.init_box = QGroupBox("初始数据点（建议录入：新卡累计测试量为 0，针长=初始针长）")
            iflay = QHBoxLayout(self.init_box)
            self.init_date = QDateEdit(QDate.currentDate())
            self.init_date.setCalendarPopup(True)
            self.init_date.setDisplayFormat("yyyy-MM-dd")
            self.init_touches = QDoubleSpinBox()
            self.init_touches.setRange(0, 1e9)
            self.init_touches.setDecimals(0)
            self.init_touches.setGroupSeparatorShown(True)
            self.init_len = QDoubleSpinBox()
            self.init_len.setRange(0, 1000)
            self.init_len.setDecimals(1)
            self.init_len.setSuffix(" um")
            iflay.addWidget(QLabel("日期"))
            iflay.addWidget(self.init_date)
            iflay.addWidget(QLabel("累计测试量"))
            iflay.addWidget(self.init_touches)
            iflay.addWidget(QLabel("针长"))
            iflay.addWidget(self.init_len)
            root.addWidget(self.init_box)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        if card_row is not None:
            self.name_edit.setText(card_row["name"])
            self.note_edit.setText(card_row["note"])
            if card_row["rated_touches"]:
                self.rated_spin.setValue(card_row["rated_touches"])
            pids = self.ctx.cards_repo.product_ids_of_card(card_row["id"])
            for pid, cb in self.product_checks:
                cb.setChecked(pid in pids)
        else:
            # 默认初始针长：取第一个产品的初始针长
            if products:
                first = next((p for p in products if p["initial_len_um"]), None)
                if first:
                    self.init_len.setValue(first["initial_len_um"])

    def _selected_pids(self) -> list[int]:
        return [pid for pid, cb in self.product_checks if cb.isChecked()]

    def _save(self):
        try:
            if self.card_row is None:
                card_id = self.ctx.cards.create_card(
                    operator=self.ctx.operator,
                    name=self.name_edit.text(),
                    product_ids=self._selected_pids(),
                    status=CardStatus.IN_STOCK,
                    rated_touches=self.rated_spin.value(),
                    in_stock_date=self.date_edit.date().toString("yyyy-MM-dd"),
                    note=self.note_edit.text(),
                )
                if self.init_touches.value() > 0 or self.init_len.value() > 0:
                    self.ctx.cards.add_update(
                        operator=self.ctx.operator, card_id=card_id,
                        update_date=self.init_date.date().toString("yyyy-MM-dd"),
                        cum_touches=self.init_touches.value(), needle_len=self.init_len.value(),
                        note="入库初始数据",
                    )
            else:
                self.ctx.cards.update_card(
                    operator=self.ctx.operator, card_id=self.card_row["id"],
                    name=self.name_edit.text(), product_ids=self._selected_pids(),
                    rated_touches=self.rated_spin.value(), note=self.note_edit.text(),
                )
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.accept()


class CardsPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        bar = QHBoxLayout()
        self.product_combo = QComboBox()
        self.status_combo = QComboBox()
        self.status_combo.addItems(["全部状态", *CardStatus.values()])
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("按针卡名称搜索…")
        self.keyword_edit.returnPressed.connect(self.refresh)
        btn_query = QPushButton("查询")
        btn_query.clicked.connect(self.refresh)
        bar.addWidget(QLabel("产品："))
        bar.addWidget(self.product_combo)
        bar.addWidget(QLabel("状态："))
        bar.addWidget(self.status_combo)
        bar.addWidget(self.keyword_edit, 1)
        bar.addWidget(btn_query)
        root.addLayout(bar)

        actions = QHBoxLayout()
        btn_new = QPushButton("＋ 新卡入库")
        btn_new.clicked.connect(self._new_card)
        btn_edit = QPushButton("编辑")
        btn_edit.setObjectName("secondaryBtn")
        btn_edit.clicked.connect(self._edit_card)
        btn_detail = QPushButton("详情 / 磨损曲线")
        btn_detail.setObjectName("secondaryBtn")
        btn_detail.clicked.connect(self._show_detail)
        btn_scrap = QPushButton("报废")
        btn_scrap.setObjectName("dangerBtn")
        btn_scrap.clicked.connect(self._scrap_card)
        btn_del = QPushButton("删除")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_card)
        for b in (btn_new, btn_edit, btn_detail, btn_scrap, btn_del):
            actions.addWidget(b)
        actions.addStretch()
        root.addLayout(actions)

        self.table = make_table(LIST_HEADERS)
        self.table.doubleClicked.connect(self._show_detail)
        root.addWidget(self.table, 1)

        self.status_combo.currentIndexChanged.connect(self.refresh)
        self.product_combo.currentIndexChanged.connect(self.refresh)
        self.refresh_products()

    def refresh_products(self):
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self.product_combo.addItem("全部产品", None)
        for p in self.ctx.products_repo.list_all():
            self.product_combo.addItem(p["name"], p["id"])
        self.product_combo.blockSignals(False)

    def refresh(self):
        self.refresh_products()
        pid = self.product_combo.currentData()
        status = self.status_combo.currentText()
        status = None if status == "全部状态" else status
        rows = self.ctx.cards_repo.list_cards(
            status=status, product_id=pid, keyword=self.keyword_edit.text().strip() or None
        )
        table_rows = []
        for r in rows:
            pred = self.ctx.prediction.predict_card(r["id"])
            ach = f"{pred.achievement_pct:.1f}%" if pred.achievement_pct is not None else "—"
            rem = f"{pred.remaining_touches:,.0f}" if pred.remaining_touches is not None else "—"
            tas = f"{pred.touches_at_scrap:,.0f}" if pred.touches_at_scrap is not None else "—"
            table_rows.append([
                r["name"], r["product_names"], r["status"], r["last_touches"], r["last_len"],
                r["last_update_date"], tas, rem, ach, pred.scrap_date or "—",
                alert_badge(pred.alert_level),
            ])
        fill_table(self.table, table_rows, align_center_cols={2, 3, 4, 5, 6, 7, 8, 9, 10})

    def _selected_id(self) -> int | None:
        idx = self.table.currentRow()
        if idx < 0:
            error_box(self, "请先在表格中选择一张针卡")
            return None
        name = self.table.item(idx, 0).text()
        card = self.ctx.cards_repo.get_by_name(name)
        return card["id"] if card else None

    def _new_card(self):
        dlg = CardFormDialog(self.ctx, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_card(self):
        cid = self._selected_id()
        if cid is None:
            return
        dlg = CardFormDialog(self.ctx, card_row=self.ctx.cards_repo.get(cid), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _show_detail(self, *args):
        cid = self._selected_id()
        if cid is None:
            return
        dlg = CardDetailDialog(self.ctx, cid, parent=self, on_changed=self.refresh)
        dlg.exec()

    def _scrap_card(self):
        cid = self._selected_id()
        if cid is None:
            return
        card = self.ctx.cards_repo.get(cid)
        if not confirm_box(self, "确认报废",
                           f"确定将针卡【{card['name']}】标记为报废吗？报废后不可恢复为可用状态。"):
            return
        try:
            self.ctx.warehouse.scrap(self.ctx.operator, cid)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()

    def _delete_card(self):
        cid = self._selected_id()
        if cid is None:
            return
        if not self.ctx.is_admin:
            error_box(self, "仅管理员可以删除针卡")
            return
        card = self.ctx.cards_repo.get(cid)
        if not confirm_box(self, "确认删除",
                           f"确定删除针卡【{card['name']}】吗？\n其全部数据更新记录将一并删除，此操作不可恢复！"):
            return
        try:
            self.ctx.cards.delete_card(self.ctx.operator, cid)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()
