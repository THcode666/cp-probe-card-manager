"""主窗口：左侧导航 + 页面栈。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, APP_VERSION
from app import paths
from app.services.app_context import AppContext
from app.ui.pages.audit_page import AuditPage
from app.ui.pages.cards_page import CardsPage
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.manual_page import ManualPage
from app.ui.pages.products_page import ProductsPage
from app.ui.pages.purchase_page import PurchasePage
from app.ui.pages.quick_update_page import QuickUpdatePage
from app.ui.pages.reports_page import ReportsPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.users_page import UsersPage
from app.ui.pages.warehouse_page import WarehousePage
from app.ui.pages.wip_page import WipPage
from app.ui.widgets.common import error_box, info_box


class PasswordDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("修改密码")
        self.setFixedWidth(340)
        form = QFormLayout(self)
        self.old_edit = QLineEdit(); self.old_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_edit = QLineEdit(); self.new_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new2_edit = QLineEdit(); self.new2_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("原密码：", self.old_edit)
        form.addRow("新密码：", self.new_edit)
        form.addRow("确认新密码：", self.new2_edit)
        btn = QPushButton("确 定")
        btn.clicked.connect(self._ok)
        form.addRow(btn)

    def _ok(self):
        if self.new_edit.text() != self.new2_edit.text():
            error_box(self, "两次输入的新密码不一致")
            return
        try:
            self.ctx.auth.change_password(
                self.ctx.current_user["id"], self.old_edit.text(), self.new_edit.text()
            )
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        info_box(self, "完成", "密码修改成功")
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1360, 820)
        self.setMinimumSize(1080, 680)
        icon_path = paths.resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ----- 顶部栏（QSS 用 QWidget#headerBar 匹配） -----
        header = QWidget()
        header.setObjectName("headerBar")
        header.setFixedHeight(58)
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(18, 0, 18, 0)
        title = QLabel(f"{APP_NAME}")
        title.setObjectName("headerTitle")
        self.user_label = QLabel()
        self.user_label.setObjectName("headerUser")
        pwd_btn = QPushButton("修改密码")
        pwd_btn.setObjectName("secondaryBtn")
        pwd_btn.clicked.connect(self._change_password)
        logout_btn = QPushButton("退出登录")
        logout_btn.setObjectName("secondaryBtn")
        logout_btn.clicked.connect(self._logout)
        hlay.addWidget(title)
        hlay.addStretch()
        hlay.addWidget(self.user_label)
        hlay.addWidget(pwd_btn)
        hlay.addWidget(logout_btn)

        # ----- 左侧导航 -----
        self.nav = QListWidget()
        self.nav.setObjectName("navList")
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # ----- 页面 -----
        self.stack = QStackedWidget()
        self._pages: list[tuple[str, QWidget]] = []
        self._add_page("主控面板", DashboardPage(ctx))
        self._add_page("针卡台账", CardsPage(ctx))
        self._add_page("数据更新", QuickUpdatePage(ctx))
        self._add_page("产品配置", ProductsPage(ctx))
        self._add_page("站点与 WIP", WipPage(ctx))
        self._add_page("仓库管理", WarehousePage(ctx))
        self._add_page("采购管理", PurchasePage(ctx))
        self._add_page("报表导出", ReportsPage(ctx))
        self._add_page("操作说明", ManualPage(ctx))
        self._add_page("系统设置", SettingsPage(ctx))
        if ctx.is_admin:
            self._add_page("操作日志", AuditPage(ctx))
        # 【用户管理】固定在最下方，所有账号可见（进入需要管理密码，见 _switch_page）
        self._add_page("用户管理", UsersPage(ctx))

        for name, page in self._pages:
            self.nav.addItem(name)
            self.stack.addWidget(page)

        self.nav.currentRowChanged.connect(self._switch_page)

        # ----- 布局 -----
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(0)
        llay.addWidget(self.nav, 1)
        root.addWidget(left)
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(header)
        rlay.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self.setCentralWidget(central)

        self._users_unlocked = False      # 本次会话是否已通过管理密码
        self._prev_nav_index = 0
        self._update_user_label()
        self.nav.setCurrentRow(0)

        # 安全提醒：仍在使用内置默认密码（延迟弹出，等主窗口完全显示后更可靠）
        if getattr(ctx, "using_default_password", False):
            from PySide6.QtCore import QTimer
            username = ctx.current_user["username"]
            QTimer.singleShot(
                600,
                lambda: QMessageBox.warning(
                    self, "安全提醒",
                    f"当前账号 {username} 仍在使用内置默认密码，任何人都可以用该密码登录。\n"
                    "请立即点击右上角【修改密码】更换！",
                ),
            )

    def _add_page(self, name: str, page: QWidget):
        self._pages.append((name, page))

    def _switch_page(self, index: int):
        if not (0 <= index < len(self._pages)):
            return
        name = self._pages[index][0]

        # 【用户管理】门禁：所有账号可见，输入管理密码后才允许进入（每次会话只需输一次）
        if name == "用户管理" and not self._users_unlocked:
            if not self._ask_module_password():
                self.nav.blockSignals(True)
                self.nav.setCurrentRow(self._prev_nav_index)
                self.nav.blockSignals(False)
                return
            self._users_unlocked = True

        self._prev_nav_index = index
        self.stack.setCurrentIndex(index)
        page = self._pages[index][1]
        if hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception as e:  # noqa: BLE001
                error_box(self, e)

    def _check_module_password(self, candidate: str) -> bool:
        """校验管理密码并记录审计（成功/失败都留痕）。独立成方法便于测试。"""
        import hmac as _hmac

        from app.constants import USER_MODULE_PASSWORD

        if _hmac.compare_digest(candidate, USER_MODULE_PASSWORD):
            # 进入模块成功同样记审计：敏感模块的每次访问都留痕（失败路径为"访问被拒"）
            self.ctx.audit_repo.log(self.ctx.operator, "用户管理", "进入用户管理", "管理密码验证通过")
            return True
        error_box(self, "管理密码不正确")
        self.ctx.audit_repo.log(self.ctx.operator, "用户管理", "访问被拒", "管理密码错误")
        return False

    def _ask_module_password(self) -> bool:
        """【用户管理】进入密码对话框。返回是否通过。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("用户管理 - 访问验证")
        dlg.setMinimumWidth(320)
        lay = QVBoxLayout(dlg)
        tip = QLabel("该模块包含账号与权限管理，请输入管理密码：")
        tip.setObjectName("tipLabel")
        pwd = QLineEdit()
        pwd.setEchoMode(QLineEdit.EchoMode.Password)
        pwd.returnPressed.connect(dlg.accept)
        lay.addWidget(tip)
        lay.addWidget(pwd)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        pwd.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        return self._check_module_password(pwd.text())

    def refresh_all(self):
        for _, page in self._pages:
            if hasattr(page, "refresh"):
                try:
                    page.refresh()
                except Exception:  # noqa: BLE001
                    pass

    def _update_user_label(self):
        u = self.ctx.current_user
        self.user_label.setText(f"{u['username']}（{u['role']}）    " if u else "")

    def _change_password(self):
        dlg = PasswordDialog(self.ctx, self)
        dlg.exec()

    def _logout(self):
        self.ctx.audit_repo.log(self.ctx.operator, "登录", "退出登录")
        self.ctx.current_user = None
        self.close()
        from app.ui.login_dialog import LoginDialog
        dlg = LoginDialog(self.ctx)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.ctx.audit_repo.log(self.ctx.operator, "登录", "重新登录")
            self._update_user_label()
            self.refresh_all()
            self.show()
