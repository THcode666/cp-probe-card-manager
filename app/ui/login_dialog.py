"""登录对话框：登录 / 注册（注册需激活码）双页签。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, APP_VERSION
from app import paths
from app.repositories.users_repo import is_builtin_default
from app.services.app_context import AppContext
from app.ui.widgets.common import error_box, info_box


class LoginDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"登录 - {APP_NAME} v{APP_VERSION}")
        self.setFixedWidth(420)
        icon_path = paths.resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 21px; font-weight: bold; color: #1F4E79;")
        sub = QLabel("线上针卡全生命周期管理")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: #7A8699; margin-bottom: 4px;")
        root.addWidget(title)
        root.addWidget(sub)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_login_tab(), "登录")
        self.tabs.addTab(self._build_register_tab(), "注册")
        root.addWidget(self.tabs)

        tip = QLabel("没有账号？切到【注册】页，向管理员索取激活码后自助开通")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #98A2B3; font-size: 11px; margin-top: 4px;")
        root.addWidget(tip)

    # ---------- 登录页 ----------

    def _build_login_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 12)
        lay.setSpacing(10)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("用户名")
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setPlaceholderText("密码")
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_edit.returnPressed.connect(self._do_login)
        lay.addWidget(self.user_edit)
        lay.addWidget(self.pwd_edit)

        btn = QPushButton("登 录")
        btn.setDefault(True)
        btn.clicked.connect(self._do_login)
        lay.addWidget(btn)
        self.user_edit.setFocus()
        return w

    # ---------- 注册页 ----------

    def _build_register_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 12)
        lay.setSpacing(10)

        self.reg_user_edit = QLineEdit()
        self.reg_user_edit.setPlaceholderText("用户名（建议用真实姓名或工号）")
        self.reg_pwd_edit = QLineEdit()
        self.reg_pwd_edit.setPlaceholderText("密码（至少 6 位）")
        self.reg_pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_pwd2_edit = QLineEdit()
        self.reg_pwd2_edit.setPlaceholderText("确认密码")
        self.reg_pwd2_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_code_edit = QLineEdit()
        self.reg_code_edit.setPlaceholderText("激活码（向管理员索取）")
        self.reg_code_edit.returnPressed.connect(self._do_register)
        for e in (self.reg_user_edit, self.reg_pwd_edit, self.reg_pwd2_edit, self.reg_code_edit):
            lay.addWidget(e)

        btn = QPushButton("注 册")
        btn.clicked.connect(self._do_register)
        lay.addWidget(btn)

        hint = QLabel("注册成功后账号角色为【工程师】；管理员可在【用户管理】中调整角色。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #98A2B3; font-size: 11px;")
        lay.addWidget(hint)
        return w

    # ---------- 动作 ----------

    def _do_login(self):
        username = self.user_edit.text().strip()
        password = self.pwd_edit.text()
        try:
            user = self.ctx.auth.login(username, password)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self._accept_user(user)

    def _do_register(self):
        username = self.reg_user_edit.text().strip()
        password = self.reg_pwd_edit.text()
        if password != self.reg_pwd2_edit.text():
            error_box(self, "两次输入的密码不一致")
            return
        try:
            self.ctx.auth.register(username, password, self.reg_code_edit.text())
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        info_box(self, "注册成功", f"账号 {username} 已开通，请登录")
        self.user_edit.setText(username)
        self.pwd_edit.clear()
        self.reg_pwd_edit.clear()
        self.reg_pwd2_edit.clear()
        self.reg_code_edit.clear()
        self.tabs.setCurrentIndex(0)
        self.pwd_edit.setFocus()

    def _accept_user(self, user):
        self.ctx.current_user = {
            "id": user["id"], "username": user["username"], "role": user["role"],
        }
        # 仍在使用内置默认密码时，由主窗口弹出安全提醒
        self.ctx.using_default_password = is_builtin_default(
            user["username"], self.pwd_edit.text()
        )
        self.accept()
