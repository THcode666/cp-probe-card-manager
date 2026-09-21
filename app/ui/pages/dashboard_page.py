"""主控面板：预警汇总 + 关键指标。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.constants import AlertLevel
from app.services.app_context import AppContext
from app.ui.widgets.common import alert_badge, fill_table, make_table, summary_card


class DashboardPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # ----- 指标卡 -----
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.card_total = summary_card("针卡总数", "0")
        self.card_stock = summary_card("在库", "0", "#2E7D32")
        self.card_use = summary_card("在用", "0", "#2E75B6")
        self.card_warn = summary_card("寿命预警卡", "0", "#C62828")
        self.card_gap = summary_card("缺卡产品", "0", "#C62828")
        self.card_buy = summary_card("需采购产品", "0", "#B26A00")
        for c in (self.card_total, self.card_stock, self.card_use, self.card_warn, self.card_gap, self.card_buy):
            cards_row.addWidget(c, 1)
        root.addLayout(cards_row)

        # 新手引导：还没有任何针卡时给出上手提示
        self.empty_tip = QLabel(
            "系统中还没有针卡数据。首次使用请按顺序操作：①【产品配置】添加产品 → "
            "②【针卡台账】新卡入库 → ③【数据更新】录入测试量与针长 → 预测和预警会自动生成。"
            "详细步骤见【操作说明】。"
        )
        self.empty_tip.setWordWrap(True)
        self.empty_tip.setStyleSheet(
            "background:#FFF8E6; border:1px solid #F2C14E; border-radius:4px;"
            "padding:10px; color:#7A5800; font-weight:bold;"
        )
        root.addWidget(self.empty_tip)

        # ----- 预警表格 -----
        tabs = QTabWidget()
        self.table_alerts = make_table(["针卡", "支持产品", "状态", "当前针长(um)", "寿命达成率", "剩余可测次数", "预计报废日期", "预警"])
        self.table_scrap = make_table(["针卡", "支持产品", "预计报废日期", "剩余可测次数", "消耗速度(次/天)", "预警"])
        self.table_gap = make_table(["产品", "在库卡数", "要求卡数", "缺口", "在途采购"])
        self.table_buy = make_table(["产品", "在库卡数", "在途", "预计缺口日期", "最晚下单日", "建议", "建议数量", "紧急程度"])
        self.table_buy.horizontalHeader().setToolTip(
            "紧急程度=采购建议的紧迫性：红色预警=已过最晚下单日，立即下单；"
            "黄色预警=最晚下单日在 7 天内，尽快下单；正常=暂不需要下单。"
        )
        tabs.addTab(self._wrap(self.table_alerts), "寿命预警")
        tabs.addTab(self._wrap(self.table_scrap), "即将报废提醒")
        tabs.addTab(self._wrap(self.table_gap), "三卡规则缺口")
        tabs.addTab(self._wrap(self.table_buy), "采购预警")
        root.addWidget(tabs, 1)

        self.footnote = QLabel("")
        self.footnote.setStyleSheet("color: #98A2B3; font-size: 11px;")
        root.addWidget(self.footnote)

    @staticmethod
    def _wrap(table: QWidget) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(table)
        return w

    def refresh(self):
        s = self.ctx.warehouse.status_counts()
        preds = self.ctx.prediction.predict_all()
        warns = [p for p in preds if p.alert_level in (AlertLevel.RED, AlertLevel.YELLOW)]
        demands = self.ctx.demand.compute_all()
        gaps = [d for d in demands if d.three_card_gap > 0]
        advices = self.ctx.purchase.advise_all()
        urgent = [a for a in advices if a.urgency in (AlertLevel.RED, AlertLevel.YELLOW)]

        self.card_total._value_label.setText(str(len(preds)))
        self.empty_tip.setVisible(len(preds) == 0)
        self.card_stock._value_label.setText(str(s.get("在库", 0)))
        self.card_use._value_label.setText(str(s.get("在用", 0)))
        self.card_warn._value_label.setText(str(len(warns)))
        self.card_gap._value_label.setText(str(len(gaps)))
        self.card_buy._value_label.setText(str(len(urgent)))

        # 寿命预警
        rows = []
        for p in sorted(warns, key=lambda x: (x.achievement_pct is None, x.achievement_pct or 0)):
            ach = f"{p.achievement_pct:.1f}%" if p.achievement_pct is not None else "—"
            rem = f"{p.remaining_touches:,.0f}" if p.remaining_touches is not None else "—"
            rows.append([p.card_name, p.product_names, p.status, p.last_len, ach, rem,
                         p.scrap_date or "—", alert_badge(p.alert_level)])
        fill_table(self.table_alerts, rows, align_center_cols={3, 4, 5, 6, 7})

        # 即将报废
        rows = []
        for p in self.ctx.prediction.scrap_remind_cards():
            rate = f"{p.daily_touch_rate:,.0f}" if p.daily_touch_rate else "—"
            rem = f"{p.remaining_touches:,.0f}" if p.remaining_touches is not None else "已到线"
            rows.append([p.card_name, p.product_names, p.scrap_date, rem, rate, alert_badge(p.alert_level)])
        fill_table(self.table_scrap, rows, align_center_cols={2, 3, 4, 5})

        # 三卡缺口（只按在库卡数判断，在用卡不计入储备）
        rows = []
        for d in gaps:
            in_transit = self.ctx.purchases_repo.in_transit_qty(d.product_id)
            rows.append([d.product_name, d.stock_cards, self.ctx.demand.min_cards,
                         d.three_card_gap, in_transit])
        fill_table(self.table_gap, rows, align_center_cols={1, 2, 3, 4, 5})

        # 采购预警
        rows = []
        for a in urgent:
            rows.append([a.product_name, a.stock_cards, a.in_transit, a.shortage_date or "—",
                         a.deadline_date or "—", a.urgency_text, a.suggested_qty, alert_badge(a.urgency)])
        fill_table(self.table_buy, rows, align_center_cols={1, 2, 3, 4, 6, 7})

        scrap_len = self.ctx.prediction.scrap_len
        self.footnote.setText(
            f"报废线 {scrap_len:g}um ｜ 寿命达成率黄色<{self.ctx.prediction.yellow_pct:g}%、"
            f"红色<{self.ctx.prediction.red_pct:g}% ｜ 三卡规则：每产品可用卡 ≥ {self.ctx.demand.min_cards} 张 ｜ "
            f"以上阈值均可在【系统设置】调整"
        )
