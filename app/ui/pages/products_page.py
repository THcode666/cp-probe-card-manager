"""产品配置页：片耗、WPH、初始针长、额定寿命、采购提前期。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.app_context import AppContext
from app.ui.widgets.common import confirm_box, error_box, fill_table, make_table


class ProductFormDialog(QDialog):
    def __init__(self, ctx: AppContext, product_row=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.product_row = product_row
        self.setWindowTitle("新增产品" if product_row is None else "编辑产品")
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如：0787")
        form.addRow("产品名称：", self.name_edit)

        self.tpw_spin = QDoubleSpinBox()
        self.tpw_spin.setRange(0, 1e9)
        self.tpw_spin.setDecimals(0)
        self.tpw_spin.setGroupSeparatorShown(True)
        self.tpw_spin.setGroupSeparatorShown(True)
        form.addRow("片耗（测一片消耗测试量/次）：", self.tpw_spin)

        self.wph_spin = QDoubleSpinBox()
        self.wph_spin.setRange(0, 1000)
        self.wph_spin.setDecimals(2)
        form.addRow("WPH（片/小时·台）：", self.wph_spin)

        self.len_spin = QDoubleSpinBox()
        self.len_spin.setRange(0, 1000)
        self.len_spin.setDecimals(1)
        self.len_spin.setSuffix(" um")
        form.addRow("新卡初始针长：", self.len_spin)

        default_rated = ctx.prediction.default_rated
        self.rated_spin = QDoubleSpinBox()
        self.rated_spin.setRange(0, 1e9)
        self.rated_spin.setDecimals(0)
        self.rated_spin.setGroupSeparatorShown(True)
        self.rated_spin.setValue(default_rated)
        self.rated_spin.setToolTip("该产品针卡测到报废线时的最大测试量（如 4800000=480W、2400000=240W）；\n"
                                   "优先级：单卡覆盖 > 产品配置 > 系统设置默认值")
        form.addRow("针卡最大测试量（额定寿命/次）：", self.rated_spin)

        self.lead_spin = QDoubleSpinBox()
        self.lead_spin.setRange(0, 365)
        self.lead_spin.setDecimals(0)
        self.lead_spin.setSuffix(" 天")
        form.addRow("采购提前期：", self.lead_spin)

        self.note_edit = QLineEdit()
        form.addRow("备注：", self.note_edit)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

        if product_row is not None:
            r = product_row
            self.name_edit.setText(r["name"])
            self.tpw_spin.setValue(r["touches_per_wafer"])
            self.wph_spin.setValue(r["wph"])
            self.len_spin.setValue(r["initial_len_um"])
            self.rated_spin.setValue(r["rated_touches"] or default_rated)
            self.lead_spin.setValue(r["lead_time_days"])
            self.note_edit.setText(r["note"])

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            error_box(self, "产品名称不能为空")
            return
        data = {
            "name": name,
            "touches_per_wafer": self.tpw_spin.value(),
            "wph": self.wph_spin.value(),
            "initial_len_um": self.len_spin.value(),
            "rated_touches": self.rated_spin.value(),
            "lead_time_days": self.lead_spin.value(),
            "note": self.note_edit.text(),
        }
        try:
            existing = self.ctx.products_repo.get_by_name(name)
            if self.product_row is None:
                if existing:
                    error_box(self, f"产品 {name} 已存在")
                    return
                pid = self.ctx.products_repo.create(data)
                self.ctx.audit_repo.log(self.ctx.operator, "产品配置", "新增产品", name)
            else:
                pid = self.product_row["id"]
                if existing and existing["id"] != pid:
                    error_box(self, f"产品名 {name} 已被使用")
                    return
                self.ctx.products_repo.update(pid, data)
                self.ctx.audit_repo.log(self.ctx.operator, "产品配置", "修改产品", name)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.accept()


class ProductsPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        bar = QHBoxLayout()
        btn_new = QPushButton("＋ 新增产品")
        btn_new.clicked.connect(self._new)
        btn_edit = QPushButton("编辑")
        btn_edit.setObjectName("secondaryBtn")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("删除产品")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete)
        for b in (btn_new, btn_edit, btn_del):
            bar.addWidget(b)
        bar.addStretch()
        tip = QLabel("双击行也可编辑")
        tip.setStyleSheet("color:#98A2B3;")
        bar.addWidget(tip)
        root.addLayout(bar)

        self.table = make_table(
            ["产品", "片耗(次/片)", "WPH(片/时)", "初始针长(um)", "针卡最大测试量(次)", "采购提前期(天)", "在库卡数", "备注"],
        )
        self.table.doubleClicked.connect(self._edit)
        root.addWidget(self.table, 1)

    def refresh(self):
        stock = self.ctx.warehouse.stock_count_by_product()
        rows = []
        for p in self.ctx.products_repo.list_all(include_inactive=True):
            rows.append([
                p["name"], p["touches_per_wafer"], p["wph"], p["initial_len_um"],
                f"{p['rated_touches']:,.0f}" if p["rated_touches"] else "默认",
                p["lead_time_days"], stock.get(p["id"], 0), p["note"],
            ])
        fill_table(self.table, rows, align_center_cols={1, 2, 3, 4, 5, 6})

    def _selected_row(self):
        idx = self.table.currentRow()
        if idx < 0:
            error_box(self, "请先选择产品")
            return None
        name = self.table.item(idx, 0).text()
        return self.ctx.products_repo.get_by_name(name)

    def _new(self):
        dlg = ProductFormDialog(self.ctx, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit(self, *args):
        row = self._selected_row()
        if row is None:
            return
        dlg = ProductFormDialog(self.ctx, product_row=row, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _delete(self):
        row = self._selected_row()
        if row is None:
            return
        pid, pname = row["id"], row["name"]

        # 前置校验：采购单引用 → 阻断；会成为"无产品"孤儿的针卡 → 阻断并列出
        po_count = self.ctx.products_repo.purchase_count(pid)
        if po_count:
            error_box(
                self,
                f"产品【{pname}】名下还有 {po_count} 张采购单，无法删除。\n"
                "请先在【采购管理 → 采购单】中删除或取消这些采购单。",
            )
            return
        orphans = [r["name"] for r in self.ctx.products_repo.orphan_cards(pid)]
        if orphans:
            error_box(
                self,
                f"针卡 {'、'.join(orphans)} 仅支持产品【{pname}】，删除后将不属于任何产品。\n"
                "请先在【针卡台账】中编辑这些针卡、关联其他产品，或将其删除/报废后再试。",
            )
            return

        if not confirm_box(
            self, "确认删除",
            f"确定删除产品【{pname}】吗？\n"
            "该产品名下的 WIP 片数与针卡关联将一并删除，此操作不可恢复！",
        ):
            return
        try:
            self.ctx.products_repo.delete(pid)
            self.ctx.audit_repo.log(self.ctx.operator, "产品配置", "删除产品", pname)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()
