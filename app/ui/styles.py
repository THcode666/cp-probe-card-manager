"""全局 QSS 样式。

原则：正文一律深色（#1F2937），浅底不配浅字；深蓝底（顶栏/导航）只配白字；
分组用 GroupBox 边框 + 标题明确切割参数区域；表格行高加大、最后一列自动拉伸填满窗口。
"""

MAIN_QSS = """
* { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 13px; color: #1F2937; }

QMainWindow, QDialog { background: #EEF1F5; }

/* ===== 左侧导航（深蓝底 + 白字，选中项高亮） ===== */
QListWidget#navList {
    background: #1F3A5F; color: #FFFFFF; border: none;
    outline: none; min-width: 172px; max-width: 172px; font-size: 14px;
}
QListWidget#navList::item { height: 44px; border: none; padding-left: 14px; color: #FFFFFF; }
QListWidget#navList::item:hover { background: #2C4F7C; color: #FFFFFF; }
QListWidget#navList::item:selected {
    background: #2E75B6; color: #FFFFFF; font-weight: bold; border-left: 4px solid #F2C14E;
}

/* ===== 顶栏（深蓝底 + 白字） ===== */
QWidget#headerBar { background: #1F3A5F; }
QWidget#headerBar QLabel { color: #FFFFFF; background: transparent; }
QLabel#headerTitle { color: #FFFFFF; font-size: 17px; font-weight: bold; }
QLabel#headerUser { color: #FFFFFF; font-weight: bold; }
QWidget#headerBar QPushButton { background: #3C6EA5; color: #FFFFFF; }
QWidget#headerBar QPushButton:hover { background: #4E82BC; }

/* ===== 指标卡 ===== */
QFrame#summaryCard { background: #FFFFFF; border: 1px solid #C9D2DB; border-radius: 6px; }
QLabel#cardValue { font-size: 24px; font-weight: bold; color: #12365E; }
QLabel#cardTitle { color: #3D4A5C; font-weight: bold; }

/* ===== 分组框（参数区域分割） ===== */
QGroupBox {
    background: #FFFFFF; border: 1px solid #C9D2DB; border-radius: 6px;
    margin-top: 12px; padding: 12px 10px 10px 10px;
    font-weight: bold; color: #12365E; font-size: 13px;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; background: #FFFFFF; }

/* ===== 表格 ===== */
QTableWidget {
    background: #FFFFFF; border: 1px solid #C9D2DB; gridline-color: #D8DEE6;
    alternate-background-color: #F7F9FB; color: #1F2937;
}
QHeaderView::section {
    background: #DCE4EC; color: #12365E; border: none; border-right: 1px solid #C4CED8;
    border-bottom: 2px solid #2E75B6; padding: 7px; font-weight: bold;
}
QTableWidget::item { padding: 5px; color: #1F2937; }
QTableWidget::item:selected { background: #B8D4F0; color: #10233A; }
QTableCornerButton::section { background: #DCE4EC; border: none; }

/* ===== 按钮 ===== */
QPushButton {
    background: #2E75B6; color: #FFFFFF; border: none; border-radius: 4px;
    padding: 7px 18px; font-weight: bold;
}
QPushButton:hover { background: #3C86C8; }
QPushButton:pressed { background: #245E93; }
QPushButton:disabled { background: #A9C4DC; }
QPushButton#secondaryBtn { background: #E4EAF0; color: #1F3A5F; border: 1px solid #C4CED8; }
QPushButton#secondaryBtn:hover { background: #D3DDE7; }
QPushButton#dangerBtn { background: #B94A48; color: #FFFFFF; }
QPushButton#dangerBtn:hover { background: #CD5C5A; }

/* ===== 输入控件 ===== */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
    background: #FFFFFF; border: 1px solid #9FB0C0; border-radius: 4px; padding: 6px 8px;
    color: #10233A; font-weight: bold;
    selection-background-color: #2E75B6; selection-color: #FFFFFF;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus { border: 2px solid #2E75B6; padding: 5px 7px; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #1F2937; selection-background-color: #2E75B6; selection-color: #FFFFFF; }

/* ===== 页签 ===== */
QTabWidget::pane { border: 1px solid #C9D2DB; background: #FFFFFF; }
QTabBar::tab { padding: 9px 22px; background: #E4EAF0; color: #3D4A5C; border: 1px solid #C9D2DB; font-weight: bold; }
QTabBar::tab:selected { background: #FFFFFF; color: #12365E; border-bottom: 3px solid #2E75B6; }

/* ===== 提示文字（保持可读的中灰，不再用过浅的灰） ===== */
QLabel#tipLabel { color: #55606E; }
QLabel#footLabel { color: #55606E; font-size: 12px; }
"""
