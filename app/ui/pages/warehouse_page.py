"""仓库管理页：状态统计、产品库存与三卡规则、流转操作、流转日志。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.constants import CardStatus
from app.services.app_context import AppContext
from app.ui.widgets.common import alert_badge, confirm_box, error_box, fill_table, make_table, summary_card


class WarehousePage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        self.card_stock = summary_card("在库", "0", "#2E7D32")
        self.card_use = summary_card("在用", "0", "#2E75B6")
        self.card_scrap = summary_card("报废", "0", "#C62828")
        for c in (self.card_stock, self.card_use, self.card_scrap):
            top.addWidget(c, 1)
        root.addLayout(top)

        self.tabs = QTabWidget()
        # 产品库存与三卡规则（只按在库数判断，在用卡不计入）
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(8, 8, 8, 8)
        note = QLabel("三卡规则按【在库】卡数判断：在用卡正在机台上消耗，不计入可调配储备。")
        note.setObjectName("tipLabel")
        l1.addWidget(note)
        self.product_table = make_table(["产品", "在库数", "要求卡数", "三卡规则", "在用数(不计入)", "在途采购"])
        l1.addWidget(self.product_table)
        self.tabs.addTab(w1, "产品库存 / 三卡规则")

        # 针卡操作
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(8, 8, 8, 8)
        bar = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItems(["在库", "在用", "报废"])
        self.status_filter.currentIndexChanged.connect(self._refresh_cards)
        btn_take = QPushButton("领用上机")
        btn_take.clicked.connect(self._take)
        btn_back = QPushButton("下机回库")
        btn_back.setObjectName("secondaryBtn")
        btn_back.clicked.connect(self._back)
        btn_scrap = QPushButton("报废")
        btn_scrap.setObjectName("dangerBtn")
        btn_scrap.clicked.connect(self._scrap)
        for w in (QLabel("状态："), self.status_filter, btn_take, btn_back, btn_scrap):
            bar.addWidget(w)
        bar.addStretch()
        l2.addLayout(bar)
        self.cards_table = make_table(["针卡名称", "支持产品", "状态", "最近更新", "累计测试量", "针长(um)"])
        self.cards_table.doubleClicked.connect(self._open_detail)
        l2.addWidget(self.cards_table, 1)
        self.tabs.addTab(w2, "针卡操作")

        # 流转日志
        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        l3.setContentsMargins(8, 8, 8, 8)
        self.log_table = make_table(["时间", "操作人", "模块", "动作", "详情"])
        l3.addWidget(self.log_table)
        self.tabs.addTab(w3, "流转与操作日志")

        root.addWidget(self.tabs, 1)

    def refresh(self):
        counts = self.ctx.warehouse.status_counts()
        self.card_stock._value_label.setText(str(counts.get("在库", 0)))
        self.card_use._value_label.setText(str(counts.get("在用", 0)))
        self.card_scrap._value_label.setText(str(counts.get("报废", 0)))
        self._refresh_products()
        self._refresh_cards()
        self._refresh_logs()

    def _refresh_products(self):
        min_cards = self.ctx.demand.min_cards
        in_transit_all = {
            p["id"]: self.ctx.purchases_repo.in_transit_qty(p["id"])
            for p in self.ctx.products_repo.list_all()
        }
        # 单条 SQL 分组统计，替代逐卡 N+1 查询
        use_count_all = self.ctx.cards_repo.count_by_product("在用")
        stock_all = self.ctx.warehouse.stock_count_by_product()
        rows = []
        for d in self.ctx.demand.compute_all():
            gap = d.three_card_gap
            rows.append([d.product_name, stock_all.get(d.product_id, 0), min_cards,
                         alert_badge("红色预警" if gap else "正常"),
                         use_count_all.get(d.product_id, 0), in_transit_all.get(d.product_id, 0)])
        fill_table(self.product_table, rows, align_center_cols={1, 2, 3, 4, 5})

    def _refresh_cards(self):
        status = self.status_filter.currentText()
        rows = []
        # 列表 SQL 已带最近一次更新（last_update_date/last_touches/last_len），无需逐卡再查
        for r in self.ctx.cards_repo.list_cards(status=status):
            rows.append([
                r["name"], r["product_names"], r["status"],
                r["last_update_date"] or "—",
                r["last_touches"],
                r["last_len"],
            ])
        fill_table(self.cards_table, rows, align_center_cols={2, 3, 4, 5})

    def _refresh_logs(self):
        rows = [
            [r["ts"], r["operator"], r["module"], r["action"], r["detail"]]
            for r in self.ctx.audit_repo.list_recent(limit=120)
        ]
        fill_table(self.log_table, rows)

    def _selected_card(self):
        idx = self.cards_table.currentRow()
        if idx < 0:
            error_box(self, "请先选择针卡")
            return None
        return self.ctx.cards_repo.get_by_name(self.cards_table.item(idx, 0).text())

    def _take(self):
        card = self._selected_card()
        if not card:
            return
        try:
            self.ctx.warehouse.take_to_machine(self.ctx.operator, card["id"])
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()

    def _back(self):
        card = self._selected_card()
        if not card:
            return
        try:
            self.ctx.warehouse.return_to_stock(self.ctx.operator, card["id"])
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()

    def _scrap(self):
        card = self._selected_card()
        if not card:
            return
        if not confirm_box(self, "确认报废", f"确定将针卡【{card['name']}】报废吗？"):
            return
        try:
            self.ctx.warehouse.scrap(self.ctx.operator, card["id"])
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()

    def _open_detail(self, *args):
        card = self._selected_card()
        if not card:
            return
        from app.ui.pages.card_detail_dialog import CardDetailDialog
        dlg = CardDetailDialog(self.ctx, card["id"], parent=self, on_changed=self.refresh)
        dlg.exec()
