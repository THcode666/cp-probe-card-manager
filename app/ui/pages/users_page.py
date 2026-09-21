"""用户管理页（仅管理员）：查看/重置/删除他人账号、角色与启停管理。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import Role
from app.services.app_context import AppContext
from app.ui.widgets.common import confirm_box, error_box, fill_table, info_box, make_table


class UserFormDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("新增用户")
        form = QFormLayout(self)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.role_combo = QComboBox()
        self.role_combo.addItems([Role.ENGINEER.value, Role.ADMIN.value])
        form.addRow("用户名：", self.username_edit)
        form.addRow("初始密码：", self.password_edit)
        form.addRow("角色：", self.role_combo)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _save(self):
        try:
            self.ctx.auth.create_user(
                self.ctx.operator, self.username_edit.text(),
                self.password_edit.text(), self.role_combo.currentText(),
            )
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.accept()


class UsersPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        bar = QHBoxLayout()
        btn_new = QPushButton("＋ 新增用户")
        btn_new.clicked.connect(self._new_user)
        btn_view = QPushButton("查看密码")
        btn_view.setObjectName("secondaryBtn")
        btn_view.clicked.connect(self._view_pwd)
        btn_reset = QPushButton("修改密码（重置）")
        btn_reset.setObjectName("secondaryBtn")
        btn_reset.clicked.connect(self._reset_pwd)
        btn_role = QPushButton("切换角色（管理员/工程师）")
        btn_role.setObjectName("secondaryBtn")
        btn_role.clicked.connect(self._toggle_role)
        btn_toggle = QPushButton("停用 / 启用")
        btn_toggle.setObjectName("secondaryBtn")
        btn_toggle.clicked.connect(self._toggle_active)
        btn_del = QPushButton("删除账号")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_user)
        for b in (btn_new, btn_view, btn_reset, btn_role, btn_toggle, btn_del):
            bar.addWidget(b)
        bar.addStretch()
        root.addLayout(bar)
        self.table = make_table(["用户名", "角色", "状态", "创建时间"])
        root.addWidget(self.table, 1)
        # 非管理员：可查看列表（需管理密码进入本模块），但增删改操作需要管理员账号
        if not ctx.is_admin:
            hint = QLabel("当前为查看模式：账号操作需要使用管理员账号登录后进行。")
            hint.setObjectName("tipLabel")
            root.addWidget(hint)
            for b in (btn_new, btn_view, btn_reset, btn_role, btn_toggle, btn_del):
                b.setEnabled(False)
                b.setToolTip("需要管理员账号登录")

    def refresh(self):
        rows = [
            [u["username"], u["role"], "启用" if u["active"] else "停用", u["created_at"]]
            for u in self.ctx.users_repo.list_all()
        ]
        fill_table(self.table, rows, align_center_cols={1, 2, 3})

    def _selected_user(self):
        idx = self.table.currentRow()
        if idx < 0:
            error_box(self, "请先选择用户")
            return None
        return self.ctx.users_repo.get_by_username(self.table.item(idx, 0).text())

    def _new_user(self):
        dlg = UserFormDialog(self.ctx, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _view_pwd(self):
        user = self._selected_user()
        if not user:
            return
        try:
            password = self.ctx.auth.reveal_password(self.ctx.operator, user["id"])
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        QMessageBox.information(
            self, "查看密码",
            f"账号：{user['username']}\n密码：{password}\n\n（本次查看已记入操作日志）",
        )

    def _reset_pwd(self):
        user = self._selected_user()
        if not user:
            return
        username = user["username"]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"修改密码 - {username}")
        form = QFormLayout(dlg)
        pwd = QLineEdit()
        pwd.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("新密码：", pwd)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.ctx.auth.reset_password(self.ctx.operator, user["id"], pwd.text())
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        info_box(self, "完成", f"已修改 {username} 的密码（新密码可随时用【查看密码】查到）")

    def _toggle_role(self):
        user = self._selected_user()
        if not user:
            return
        new_role = Role.ADMIN.value if user["role"] == Role.ENGINEER.value else Role.ENGINEER.value
        try:
            self.ctx.auth.set_role(self.ctx.operator, user["id"], new_role)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()

    def _toggle_active(self):
        user = self._selected_user()
        if not user:
            return
        active = not bool(user["active"])
        try:
            self.ctx.auth.set_active(self.ctx.operator, user["id"], active)
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()

    def _delete_user(self):
        user = self._selected_user()
        if not user:
            return
        if not confirm_box(
            self, "确认删除",
            f"确定删除账号【{user['username']}】吗？\n该账号将无法登录，操作会记入日志，不可恢复！",
        ):
            return
        try:
            self.ctx.auth.delete_user(self.ctx.operator, user["id"])
        except Exception as e:  # noqa: BLE001
            error_box(self, e)
            return
        self.refresh()
