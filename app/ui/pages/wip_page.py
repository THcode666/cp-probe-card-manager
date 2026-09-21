"""站点与 WIP 页。

站点分两级：
- N1 站点：前段，距 CP 时间过长，WIP 只记【数量】（展示未来待流入量），不参与时间推算；
- N2 站点：临近 CP，WIP 记【数量 + 到 CP 时间】，按站点顺序推算未来到达量与测试量需求。
流程：N1 各站点 → N2 各站点 → CP。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.app_context import AppContext
from app.ui.widgets.common import confirm_box, error_box, fill_table, make_table


class StationFormDialog(QDialog):
    def __init__(self, ctx: AppContext, station=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.station = station
        self.setWindowTitle("新增站点" if station is None else "编辑站点")
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        form.addRow("站点名称：", self.name_edit)

        self.stage_combo = QComboBox()
        self.stage_combo.addItem("N2（临近 CP：记到 CP 时间 + 数量，参与需求推算）", "N2")
        self.stage_combo.addItem("N1（前段：只记数量，不参与时间推算）", "N1")
        form.addRow("站点级别：", self.stage_combo)

        self.days_spin = QDoubleSpinBox()
        self.days_spin.setRange(0, 365)
        self.days_spin.setDecimals(1)
        self.days_spin.setSuffix(" 天")
        self.days_spin.setToolTip("N2 站点：从该站点流转到 CP 需要的时间，用于推算 WIP 何时到达 CP；\n"
                                  "N1 站点：距 CP 过远不计算时间，此值仅作参考")
        form.addRow("到 CP 周转时间：", self.days_spin)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        if station is not None:
            self.name_edit.setText(station["name"])
            self.days_spin.setValue(station["days_to_cp"])
            idx = self.stage_combo.findData(station["stage"] if "stage" in station.keys() else "N2")
            self.stage_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            error_box(self, "站点名称不能为空")
            return
        stage = self.stage_combo.currentData()
        days = self.days_spin.value() if stage == "N2" else 0.0
        try:
            if self.station is None:
                self.ctx.planning_repo.create_station(name, days, stage)
            else:
                self.ctx.planning_repo.update_station(self.station["id"], name, days, True, stage)
            self.ctx.audit_repo.log(self.ctx.operator, "站点WIP", "保存站点", f"{stage} {name}")
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.accept()


class WipPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        # ----- 站点配置 -----
        station_box = QGroupBox("站点配置（N1 前段只记数量；N2 按到 CP 时间推算到达量）")
        slay = QVBoxLayout(station_box)
        bar = QHBoxLayout()
        btn_add = QPushButton("＋ 新增站点")
        btn_add.clicked.connect(self._add_station)
        btn_edit = QPushButton("编辑选中站点")
        btn_edit.setObjectName("secondaryBtn")
        btn_edit.clicked.connect(self._edit_station)
        btn_del = QPushButton("删除选中站点")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_station)
        for b in (btn_add, btn_edit, btn_del):
            bar.addWidget(b)
        bar.addStretch()
        slay.addLayout(bar)
        self.station_table = make_table(["站点", "级别", "到 CP 时间(天)"])
        self.station_table.setMaximumHeight(170)
        slay.addWidget(self.station_table)
        root.addWidget(station_box)

        # ----- WIP 录入：N2（参与推算）+ N1（只记数量） -----
        wip_split = QHBoxLayout()
        wip_split.setSpacing(10)

        n2_box = QGroupBox("N2 WIP（临近 CP：数量 + 到 CP 时间 → 推算未来需求）")
        n2lay = QVBoxLayout(n2_box)
        self.n2_table = make_table([])
        n2lay.addWidget(self.n2_table, 1)
        wip_split.addWidget(n2_box, 3)

        n1_box = QGroupBox("N1 WIP（前段：只记数量，不计算时间）")
        n1lay = QVBoxLayout(n1_box)
        self.n1_table = make_table([])
        n1lay.addWidget(self.n1_table, 1)
        wip_split.addWidget(n1_box, 2)

        root.addLayout(wip_split, 1)

        # 放开 WIP 单元格编辑（产品名列在填充时单独设为只读）
        editable = (
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.SelectedClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.AnyKeyPressed
        )
        self.n2_table.setEditTriggers(editable)
        self.n1_table.setEditTriggers(editable)

        # 单元格改动立即保存（避免"改了但没生效"），填充期间挂起
        self._filling = False
        self.n2_table.itemChanged.connect(lambda item: self._on_cell_changed(item, "N2"))
        self.n1_table.itemChanged.connect(lambda item: self._on_cell_changed(item, "N1"))

        save_bar = QHBoxLayout()
        btn_save = QPushButton("保存全部 WIP（N1 + N2）")
        btn_save.clicked.connect(self._save_wip)
        save_bar.addWidget(btn_save)
        save_bar.addStretch()
        self.tip_label = QLabel("")
        self.tip_label.setObjectName("tipLabel")
        save_bar.addWidget(self.tip_label)
        root.addLayout(save_bar)

    # ---------- 渲染 ----------

    def refresh(self):
        self._refresh_stations()
        self._refresh_wip()

    def _refresh_stations(self):
        rows = [
            [s["name"], s["stage"] if "stage" in s.keys() else "N2",
             s["days_to_cp"] if s["stage"] == "N2" else "不计时间"]
            for s in self.ctx.planning_repo.list_stations(include_inactive=True)
        ]
        fill_table(self.station_table, rows, align_center_cols={1, 2})

    def _station_seq_label(self, stations: list, index: int) -> str:
        """N2 站点按到 CP 时间升序显示顺序：CP 前第 1 站、第 2 站…"""
        return f"CP前第{len(stations) - index}站"

    def _fill_matrix(self, table, stations: list, products: list, stage: str):
        headers = ["产品 \\ 站点"]
        if stage == "N2":
            for i, s in enumerate(stations):
                seq = self._station_seq_label(stations, i)
                headers.append(f"{s['name']}\n{seq}\n到CP {s['days_to_cp']:g}天")
        else:
            for s in stations:
                headers.append(f"{s['name']}\n(只记数量)")
        self._filling = True
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(products))
        table.verticalHeader().setDefaultSectionSize(36)
        for r, p in enumerate(products):
            name_item = QTableWidgetItem(p["name"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(r, 0, name_item)
            wip = self.ctx.planning_repo.list_wip(p["id"])
            for c, s in enumerate(stations, start=1):
                qty = next((w["qty"] for w in wip if w["station_id"] == s["id"]), 0)
                item = QTableWidgetItem(str(qty) if qty else "")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(r, c, item)
        # 列宽随内容自适应，保证表头/数字完整显示
        header = table.horizontalHeader()
        header.setMinimumSectionSize(90)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self._filling = False

    def _refresh_wip(self):
        products = self.ctx.products_repo.list_all()
        stations = self.ctx.planning_repo.list_stations(include_inactive=True)
        n1 = [s for s in stations if s["stage"] == "N1"]
        n2 = [s for s in stations if s["stage"] == "N2"]
        self._fill_matrix(self.n2_table, n2, products, "N2")
        self._fill_matrix(self.n1_table, n1, products, "N1")
        horizon = self.ctx.demand.horizon_days
        self.tip_label.setText(
            f"N2 WIP 按各站到 CP 时间推算未来 {horizon} 天到达量与测试量需求；"
            f"N1 WIP 只作数量参考（当前页面显示 {len(n1)} 个 N1 站、{len(n2)} 个 N2 站）"
        )

    # ---------- 操作 ----------

    def _save_wip(self):
        products = self.ctx.products_repo.list_all()
        stations = self.ctx.planning_repo.list_stations(include_inactive=True)
        tables = {"N1": self.n1_table, "N2": self.n2_table}
        try:
            for stage, table in tables.items():
                stage_stations = [s for s in stations if s["stage"] == stage]
                for r, p in enumerate(products):
                    for c, s in enumerate(stage_stations, start=1):
                        item = table.item(r, c)
                        text = (item.text().strip() if item else "") or "0"
                        qty = int(float(text))
                        if not (0 <= qty <= 1_000_000_000):
                            raise ValueError(
                                f"WIP 片数须为 0 ~ 1,000,000,000 的整数"
                                f"（{p['name']} × {s['name']} 填了 {qty}）"
                            )
                        self.ctx.planning_repo.set_wip(p["id"], s["id"], qty, self.ctx.operator)
            self.ctx.audit_repo.log(self.ctx.operator, "站点WIP", "批量保存WIP",
                                    f"{len(products)} 产品（N1+N2 全部站点）")
        except ValueError as e:
            error_box(self, str(e) or "WIP 片数必须是整数")
            return
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self._refresh_wip()

    def _add_station(self):
        dlg = StationFormDialog(self.ctx, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_cell_changed(self, item, stage: str):
        """单元格改动立即入库：改完即生效，无需再点保存。非法输入回退原值。"""
        if self._filling or item is None or item.column() == 0:
            return
        stations = [s for s in self.ctx.planning_repo.list_stations(include_inactive=True)
                    if s["stage"] == stage]
        products = self.ctx.products_repo.list_all()
        r, c = item.row(), item.column()
        if r >= len(products) or c - 1 >= len(stations):
            return
        product, station = products[r], stations[c - 1]

        raw = (item.text().strip() if item.text() else "") or "0"
        old_wip = self.ctx.planning_repo.list_wip(product["id"])
        old_qty = next((w["qty"] for w in old_wip if w["station_id"] == station["id"]), 0)
        try:
            qty = int(float(raw))
            if not (0 <= qty <= 1_000_000_000):
                raise ValueError
        except ValueError:
            error_box(self, "WIP 片数须为 0 ~ 1,000,000,000 的整数，已恢复原值")
            self._filling = True
            item.setText(str(old_qty) if old_qty else "")
            self._filling = False
            return
        try:
            self.ctx.planning_repo.set_wip(product["id"], station["id"], qty, self.ctx.operator)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)

    def _delete_station(self):
        """彻底删除站点：其 WIP 数据随外键级联一并删除（需确认）。"""
        idx = self.station_table.currentRow()
        if idx < 0:
            error_box(self, "请先选择站点")
            return
        name = self.station_table.item(idx, 0).text()
        station = next(
            (s for s in self.ctx.planning_repo.list_stations(include_inactive=True) if s["name"] == name),
            None,
        )
        if not station:
            return
        stage = station["stage"] if "stage" in station.keys() else "N2"
        wip_rows = [w for w in self.ctx.planning_repo.list_wip() if w["station_id"] == station["id"]]
        wip_qty = sum(w["qty"] for w in wip_rows)
        qty_info = f"，站点上的 {wip_qty} 片 WIP 数据将一并删除" if wip_qty else ""
        if not confirm_box(
            self, "确认删除",
            f"确定删除{stage}站点【{name}】吗？{qty_info}。\n此操作不可恢复！",
        ):
            return
        try:
            self.ctx.planning_repo.delete_station(station["id"])
            self.ctx.audit_repo.log(self.ctx.operator, "站点WIP", "删除站点",
                                    f"{stage} {name}（含 WIP {wip_qty} 片）")
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()

    def _edit_station(self):
        idx = self.station_table.currentRow()
        if idx < 0:
            error_box(self, "请先选择站点")
            return
        name = self.station_table.item(idx, 0).text()
        station = next(
            (s for s in self.ctx.planning_repo.list_stations(include_inactive=True) if s["name"] == name), None
        )
        if station is None:
            return
        dlg = StationFormDialog(self.ctx, station=station, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
