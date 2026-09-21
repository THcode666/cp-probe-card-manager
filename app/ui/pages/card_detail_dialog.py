"""针卡详情对话框：信息 + 磨损曲线图 + 数据点历史 + 快速补录。"""

from __future__ import annotations

import html

import pyqtgraph as pg
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.services.app_context import AppContext
from app.ui.widgets.common import (
    alert_badge,
    confirm_box,
    error_box,
    fill_table,
    make_table,
    show_warnings,
)

pg.setConfigOptions(antialias=True, background="w", foreground="k")


class CardDetailDialog(QDialog):
    def __init__(self, ctx: AppContext, card_id: int, parent=None, on_changed=None):
        super().__init__(parent)
        self.ctx = ctx
        self.card_id = card_id
        self.on_changed = on_changed
        self.setWindowTitle("针卡详情")
        self.resize(980, 680)
        root = QVBoxLayout(self)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("font-size: 13px;")
        root.addWidget(self.info_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, 1)

        # ----- 曲线图 -----
        self.plot = pg.PlotWidget()
        self.plot.addLegend(offset=(10, 10))
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "累计测试量（万次）")
        self.plot.setLabel("left", "针长 (um)")
        splitter.addWidget(self.plot)

        # ----- 数据点 -----
        data_widget = QWidget()
        dlay = QVBoxLayout(data_widget)
        dlay.setContentsMargins(0, 4, 0, 0)
        self.updates_table = make_table(["日期", "累计测试量(次)", "针长(um)", "操作人", "备注", ""])
        dlay.addWidget(self.updates_table, 1)

        form_box = QGroupBox("补录数据点")
        flay = QHBoxLayout(form_box)
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
        self.note_edit.setPlaceholderText("备注（可空）")
        btn = QPushButton("保存")
        btn.clicked.connect(self._add_point)
        for w in (QLabel("日期"), self.date_edit, QLabel("累计测试量"), self.touches_spin,
                  QLabel("针长"), self.len_spin, QLabel("备注"), self.note_edit, btn):
            flay.addWidget(w)
        dlay.addWidget(form_box)
        splitter.addWidget(data_widget)
        splitter.setSizes([360, 300])

        self.refresh()

    # ---------- 渲染 ----------

    def refresh(self):
        pred = self.ctx.prediction.predict_card(self.card_id)
        scrap_len = self.ctx.prediction.scrap_len

        self.plot.clear()
        line = pg.InfiniteLine(
            pos=scrap_len, angle=0, pen=pg.mkPen("#C62828", style=Qt.PenStyle.DashLine, width=1.5)
        )
        self.plot.addItem(line)
        label = pg.TextItem(f"报废线 {scrap_len:g}um", color="#C62828")
        label.setPos(0, scrap_len)
        self.plot.addItem(label)

        pts = self.ctx.cards_repo.update_points_for_card(self.card_id)
        if pts:
            xs = [p["cum_touches"] / 1e4 for p in pts]
            ys = [p["needle_len"] for p in pts]
            self.plot.plot(
                xs, ys, pen=None, symbol="o", symbolSize=9,
                symbolBrush="#2E75B6", name="实测数据点",
            )
            if pred.curve_slope is not None and pred.touches_at_scrap:
                x_end = pred.touches_at_scrap / 1e4
                x0, x1 = 0.0, max(x_end * 1.05, max(xs) * 1.1)
                fit_x = [x0, x1]
                fit_y = [pred.curve_slope * v * 1e4 + pred.curve_intercept for v in fit_x]
                color = "#2E7D32" if pred.curve_source == "own" else "#B26A00"
                text = "单卡拟合" if pred.curve_source == "own" else "同类型平均曲线"
                self.plot.plot(
                    fit_x, fit_y,
                    pen=pg.mkPen(color, width=2, style=Qt.PenStyle.DashLine), name=text,
                )

        # 用户自由输入的字段做 HTML 转义，防止富文本注入破坏界面
        name = html.escape(pred.card_name)
        products = html.escape(pred.product_names)
        status = html.escape(pred.status)
        curve_txt = "单卡拟合" if pred.curve_source == "own" else "同类型平均曲线"
        info = [f"<b style='font-size:15px'>{name}</b>",
                f"支持产品：{products or '—'}　　状态：{status}　　数据点：{pred.points_count} 个",
                (f"当前累计测试量：{pred.last_touches:,.0f} 次" if pred.last_touches is not None
                 else "当前累计测试量：—"),
                (f"当前针长：{pred.last_len:g}um" if pred.last_len is not None else "当前针长：—"),
                f"额定寿命：{pred.rated_touches:,.0f} 次",
                (f"预测到报废线时累计测试量：<b>{pred.touches_at_scrap:,.0f} 次</b>（依据：{curve_txt}）"
                 if pred.touches_at_scrap is not None
                 else "预测：数据点不足，无法预测（至少 2 个数据点，3 个更佳）"),
                (f"剩余可测：<b>{pred.remaining_touches:,.0f} 次</b>"
                 if pred.remaining_touches is not None else "剩余可测：—"),
                (f"寿命达成率：<b>{pred.achievement_pct:.1f}%</b>（额定 {pred.rated_touches:,.0f}）"
                 if pred.achievement_pct is not None else "寿命达成率：—"),
                (f"消耗速度：{pred.daily_touch_rate:,.0f} 次/天　　预计报废日期：<b>{pred.scrap_date}</b>"
                 if pred.daily_touch_rate else "消耗速度：—（需至少两次不同日期的数据）")]
        self.info_label.setText("<br/>".join(info))
        self.setWindowTitle(f"针卡详情 - {pred.card_name}")

        rows = []
        for u in self.ctx.cards_repo.updates_for_card(self.card_id):
            del_btn = QPushButton("删除") if self.ctx.is_admin else QLabel("")
            if isinstance(del_btn, QPushButton):
                del_btn.setObjectName("secondaryBtn")
                uid, uname = u["id"], pred.card_name
                del_btn.clicked.connect(lambda _=False, i=uid, n=uname: self._del_point(i, n))
            rows.append([u["update_date"], u["cum_touches"], u["needle_len"], u["operator"], u["note"], del_btn])
        fill_table(self.updates_table, rows, align_center_cols={0, 1, 2, 3})

        if pred.last_touches is not None and self.touches_spin.value() == 0:
            self.touches_spin.setValue(pred.last_touches)

    # ---------- 操作 ----------

    def _add_point(self):
        try:
            warnings = self.ctx.cards.add_update(
                operator=self.ctx.operator,
                card_id=self.card_id,
                update_date=self.date_edit.date().toString("yyyy-MM-dd"),
                cum_touches=self.touches_spin.value(),
                needle_len=self.len_spin.value(),
                note=self.note_edit.text(),
            )
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.note_edit.clear()
        self.refresh()
        if self.on_changed:
            self.on_changed()
        show_warnings(self, warnings)

    def _del_point(self, update_id: int, card_name: str):
        if not confirm_box(self, "确认", "确定删除该数据点吗？"):
            return
        try:
            self.ctx.cards.delete_update(self.ctx.operator, update_id, card_name)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()
        if self.on_changed:
            self.on_changed()
