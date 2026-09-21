"""通用界面组件与工具函数。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.constants import AlertLevel

LEVEL_COLORS = {
    AlertLevel.OK: ("#2E7D32", "#E6F4EA"),
    AlertLevel.YELLOW: ("#B26A00", "#FFF4E0"),
    AlertLevel.RED: ("#C62828", "#FDE7E7"),
    AlertLevel.UNKNOWN: ("#5F6B7A", "#EEF1F4"),
}


def alert_badge(level: str) -> "QLabel":
    """生成带底色的预警级别标签。

    按字体实测宽度设置最小宽度（QLabel 的 sizeHint 不含样式表 padding，
    不加宽度会导致"红色预警"等文字被列宽截断），保证任何表格中都完整显示。
    """
    fg, bg = LEVEL_COLORS.get(level, LEVEL_COLORS[AlertLevel.UNKNOWN])
    lab = QLabel(level)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    fm = QFontMetrics(lab.font())
    text_w = fm.horizontalAdvance(level)
    lab.setMinimumWidth(text_w + 28)  # 左右 padding 10px×2 + 边距余量
    lab.setMinimumHeight(24)
    lab.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    lab.setStyleSheet(
        f"color: {fg}; background: {bg}; border-radius: 9px; padding: 2px 10px; font-weight: bold;"
    )
    return lab


def make_table(headers: list[str], stretch_all: bool = False) -> QTableWidget:
    """构建只读表格。所有列随内容自适应宽度（保证文字完整显示），末列拉伸填满。"""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
    header.setMinimumSectionSize(56)
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)  # 全部列随内容自适应
    header.setStretchLastSection(True)
    table.verticalHeader().setDefaultSectionSize(34)
    return table


def fill_table(table: QTableWidget, rows: list[list], align_center_cols: set[int] | None = None):
    align_center_cols = align_center_cols or set()
    table.setRowCount(0)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem()
            if isinstance(value, QWidget):
                table.setCellWidget(r, c, value)
                continue
            if value is None:
                text = ""
            elif isinstance(value, float):
                text = f"{value:,.0f}" if abs(value) >= 1000 else f"{value:g}"
            else:
                text = str(value)
            item.setText(text)
            if c in align_center_cols:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, c, item)


def summary_card(title: str, value: str, color: str = "#1F4E79") -> QFrame:
    frame = QFrame()
    frame.setObjectName("summaryCard")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 10, 14, 10)
    v = QLabel(value)
    v.setObjectName("cardValue")
    v.setStyleSheet(f"color: {color};")
    t = QLabel(title)
    t.setObjectName("cardTitle")
    lay.addWidget(v)
    lay.addWidget(t)
    frame._value_label = v  # 便于刷新
    return frame


def error_box(parent: QWidget, exc: Exception | str):
    msg = str(exc)
    if msg.startswith("[Errno") or "sqlite3" in msg.lower():
        msg = f"数据库操作失败：{msg}"
    QMessageBox.critical(parent, "操作失败", msg)


def info_box(parent: QWidget, title: str, text: str):
    QMessageBox.information(parent, title, text)


def confirm_box(parent: QWidget, title: str, text: str) -> bool:
    return QMessageBox.question(
        parent, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    ) == QMessageBox.StandardButton.Yes


def show_warnings(parent: QWidget, warnings: list[str]):
    if warnings:
        QMessageBox.warning(parent, "注意", "数据已保存，但有以下提醒：\n\n" + "\n".join(f"· {w}" for w in warnings))
