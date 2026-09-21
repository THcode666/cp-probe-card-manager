"""采购管理页：采购预警建议 + 采购单登记跟踪。"""

from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.constants import PurchaseStatus
from app.services.app_context import AppContext
from app.ui.widgets.common import alert_badge, confirm_box, error_box, fill_table, make_table


class PurchaseFormDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None, product_id=None, qty=0):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("登记采购单")
        self.setMinimumWidth(400)
        form = QFormLayout(self)
        self.product_combo = QComboBox()
        for p in ctx.products_repo.list_all():
            self.product_combo.addItem(p["name"], p["id"])
        if product_id:
            idx = self.product_combo.findData(product_id)
            if idx >= 0:
                self.product_combo.setCurrentIndex(idx)
        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setRange(1, 999)
        self.qty_spin.setDecimals(0)
        self.qty_spin.setValue(max(1, qty))
        self.order_date = QDateEdit(QDate.currentDate())
        self.order_date.setCalendarPopup(True)
        self.order_date.setDisplayFormat("yyyy-MM-dd")
        self.eta_date = QDateEdit(QDate.currentDate().addDays(30))
        self.eta_date.setCalendarPopup(True)
        self.eta_date.setDisplayFormat("yyyy-MM-dd")
        self.note_edit = QLineEdit()
        form.addRow("产品：", self.product_combo)
        form.addRow("采购数量：", self.qty_spin)
        form.addRow("下单日期：", self.order_date)
        form.addRow("预计到货：", self.eta_date)
        form.addRow("备注：", self.note_edit)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.product_combo.currentIndexChanged.connect(self._auto_eta)
        self._auto_eta()

    def _auto_eta(self):
        pid = self.product_combo.currentData()
        p = self.ctx.products_repo.get(pid)
        if p and p["lead_time_days"]:
            self.eta_date.setDate(QDate.currentDate().addDays(int(p["lead_time_days"])))

    def _save(self):
        try:
            self.ctx.purchases_repo.create(
                product_id=self.product_combo.currentData(),
                qty=int(self.qty_spin.value()),
                order_date=self.order_date.date().toString("yyyy-MM-dd"),
                eta_date=self.eta_date.date().toString("yyyy-MM-dd"),
                operator=self.ctx.operator,
                note=self.note_edit.text(),
            )
            self.ctx.audit_repo.log(
                self.ctx.operator, "采购管理", "登记采购单",
                f"{self.product_combo.currentText()} × {int(self.qty_spin.value())}",
            )
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.accept()


class PurchasePage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        self.tabs = QTabWidget()

        # ----- 建议 -----
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(8, 8, 8, 8)
        bar = QHBoxLayout()
        btn_new_from_advice = QPushButton("按选中建议登记采购单")
        btn_new_from_advice.clicked.connect(self._order_from_advice)
        bar.addWidget(btn_new_from_advice)
        bar.addStretch()
        self.horizon_tip = QLabel("")
        self.horizon_tip.setObjectName("tipLabel")
        self.horizon_tip.setWordWrap(True)
        bar.addWidget(self.horizon_tip)
        l1.addLayout(bar)
        self.advice_table = make_table(
            ["产品", "在库卡数", "三卡缺口", "在途数量", "测试量需求(次)", "现有总余量(次)",
             "预计缺口日期", "最晚下单日", "建议", "建议采购数量", "紧急程度"]
        )
        self.advice_table.horizontalHeader().setToolTip(
            "紧急程度=采购建议的紧迫性：\n"
            "· 红色预警：已过最晚下单日，请立即下单；\n"
            "· 黄色预警：最晚下单日在 7 天内，请尽快下单；\n"
            "· 正常：展望期内暂不需要下单（若建议数量>0，是三卡规则缺口）。"
        )
        self.advice_table.doubleClicked.connect(self._order_from_advice)
        l1.addWidget(self.advice_table, 1)
        self.tabs.addTab(w1, "采购预警与建议")

        # ----- 采购单 -----
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(8, 8, 8, 8)
        bar2 = QHBoxLayout()
        btn_new = QPushButton("＋ 登记采购单")
        btn_new.clicked.connect(self._new_po)
        self.po_status = QComboBox()
        self.po_status.addItems(["全部", *PurchaseStatus.values()])
        self.po_status.currentIndexChanged.connect(self._refresh_pos)
        btn_recv = QPushButton("标记到货")
        btn_recv.setObjectName("secondaryBtn")
        btn_recv.clicked.connect(self._receive)
        btn_cancel = QPushButton("取消采购单")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self._cancel)
        btn_del = QPushButton("删除采购单")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_po)
        for w in (btn_new, QLabel("筛选："), self.po_status, btn_recv, btn_cancel, btn_del):
            bar2.addWidget(w)
        bar2.addStretch()
        l2.addLayout(bar2)
        self.po_table = make_table(["ID", "产品", "数量", "下单日期", "预计到货", "状态", "操作人", "备注"])
        l2.addWidget(self.po_table, 1)
        self.tabs.addTab(w2, "采购单")

        root.addWidget(self.tabs, 1)

    def refresh(self):
        self._refresh_advice()
        self._refresh_pos()

    def _refresh_advice(self):
        rows = []
        for a in self.ctx.purchase.advise_all():
            rows.append([
                a.product_name, a.stock_cards, a.three_card_gap, a.in_transit,
                a.total_touches_needed, a.capacity_touches,
                a.shortage_date or "无", a.deadline_date or "—",
                a.urgency_text, a.suggested_qty, alert_badge(a.urgency),
            ])
        fill_table(self.advice_table, rows, align_center_cols={1, 2, 3, 4, 5, 6, 7, 9, 10})
        self.horizon_tip.setText(
            f"需求展望 {self.ctx.demand.horizon_days} 天；采购缓冲 {self.ctx.purchase.buffer_days:g} 天"
            "（均可在系统设置调整）。紧急程度说明：红色预警=已过最晚下单日，立即下单；"
            "黄色预警=最晚下单日在 7 天内，尽快下单；正常=暂不需要下单。"
        )

    def _refresh_pos(self):
        status = self.po_status.currentText()
        pos = self.ctx.purchases_repo.list_all(status=None if status == "全部" else status)
        rows = [
            [p["id"], p["product_name"], p["qty"], p["order_date"], p["eta_date"],
             p["status"], p["operator"], p["note"]]
            for p in pos
        ]
        fill_table(self.po_table, rows, align_center_cols={0, 2, 3, 4, 5, 6})

    def _selected_po(self):
        idx = self.po_table.currentRow()
        if idx < 0:
            error_box(self, "请先选择采购单")
            return None
        po_id = int(self.po_table.item(idx, 0).text())
        pos = self.ctx.purchases_repo.list_all()
        return next((p for p in pos if p["id"] == po_id), None)

    def _order_from_advice(self, *args):
        idx = self.advice_table.currentRow()
        product_id = None
        qty = 0
        if idx >= 0:
            name = self.advice_table.item(idx, 0).text()
            p = self.ctx.products_repo.get_by_name(name)
            product_id = p["id"] if p else None
            qty = int(self.advice_table.item(idx, 9).text() or 0)
        dlg = PurchaseFormDialog(self.ctx, parent=self, product_id=product_id, qty=qty)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _new_po(self):
        dlg = PurchaseFormDialog(self.ctx, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _receive(self):
        po = self._selected_po()
        if not po:
            return
        if po["status"] != PurchaseStatus.ORDERED:
            error_box(self, "仅【已下单】状态的采购单可以标记到货")
            return
        self.ctx.purchases_repo.set_status(po["id"], PurchaseStatus.RECEIVED)
        self.ctx.audit_repo.log(
            self.ctx.operator, "采购管理", "标记到货",
            f"{po['product_name']} × {po['qty']}（到货后请用【针卡台账-新卡入库】录入卡片）",
        )
        self.refresh()

    def _cancel(self):
        po = self._selected_po()
        if not po:
            return
        if po["status"] != PurchaseStatus.ORDERED:
            error_box(self, "仅【已下单】状态的采购单可以取消")
            return
        if not confirm_box(self, "确认", f"确定取消采购单（{po['product_name']} × {po['qty']}）吗？"):
            return
        self.ctx.purchases_repo.set_status(po["id"], PurchaseStatus.CANCELLED)
        self.ctx.audit_repo.log(self.ctx.operator, "采购管理", "取消采购单", f"{po['product_name']} × {po['qty']}")
        self.refresh()

    def _delete_po(self):
        po = self._selected_po()
        if not po:
            return
        transit_note = (
            "该单当前计入在途数量，删除后采购缺口预警将不再扣减它。" if po["status"] == PurchaseStatus.ORDERED else ""
        )
        if not confirm_box(
            self, "确认删除",
            f"确定删除采购单（{po['product_name']} × {po['qty']}，{po['status']}）吗？{transit_note}\n此操作不可恢复！",
        ):
            return
        try:
            self.ctx.purchases_repo.delete(po["id"])
            self.ctx.audit_repo.log(self.ctx.operator, "采购管理", "删除采购单",
                                    f"{po['product_name']} × {po['qty']}（{po['status']}）")
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()
