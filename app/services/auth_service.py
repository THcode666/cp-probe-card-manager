"""登录认证、自助注册、密码修改、用户管理。

安全设计：
- 登录连续失败 5 次锁定账号 5 分钟（防暴力破解）；
- 用户管理类接口（新增/删除/改密/查密/角色/启停）在服务层强制校验操作人是
  启用状态的管理员——即使有人绕过界面直接调用业务层也无法越权。
"""

from __future__ import annotations

import hmac
import sqlite3

from app.constants import ACTIVATION_CODE
from app.repositories import users_repo
from app.repositories.audit_repo import AuditRepo
from app.repositories.settings_repo import SettingsRepo
from app.repositories.users_repo import UsersRepo


class AuthService:
    def __init__(self, users_repo: UsersRepo, audit_repo: AuditRepo, settings_repo: SettingsRepo):
        self.users = users_repo
        self.audit = audit_repo
        self.settings = settings_repo

    # ---------- 内部校验 ----------

    def _require_admin(self, operator: str) -> None:
        """服务层权限校验：操作人必须是启用状态的管理员。"""
        u = self.users.get_by_username(operator.strip())
        if not u or not u["active"] or u["role"] != "管理员":
            self.audit.log(operator, "用户管理", "越权尝试", "非管理员调用管理接口")
            raise ValueError("需要管理员权限")

    @staticmethod
    def _check_username(username: str) -> str:
        username = username.strip()
        if not username:
            raise ValueError("用户名不能为空")
        if len(username) > 32:
            raise ValueError("用户名过长（最多 32 个字符）")
        return username

    # ---------- 登录 ----------

    def login(self, username: str, password: str) -> sqlite3.Row:
        username = username.strip()
        user = self.users.get_by_username(username)
        if not user:
            self.audit.log(username or "?", "登录", "登录失败")
            raise ValueError("用户名或密码错误，或账号已停用")

        locked_until = user["locked_until"]
        if locked_until:
            try:
                self.users.clear_lock_if_expired(user["id"], locked_until)
                user = self.users.get(user["id"])
                locked_until = user["locked_until"]
            except ValueError:
                pass
        if locked_until:
            self.audit.log(username, "登录", "登录被拒", f"账号锁定至 {locked_until}")
            raise ValueError(f"登录失败次数过多，账号已锁定至 {locked_until}，请联系管理员或稍后再试")

        if not user["active"]:
            self.audit.log(username, "登录", "登录失败")
            raise ValueError("用户名或密码错误，或账号已停用")

        if users_repo.verify_password(password, user["salt"], user["password_hash"]):
            self.users.record_login_success(user["id"])
            self.audit.log(username, "登录", "登录成功")
            return user

        locked = self.users.record_login_failure(user["id"])
        if locked:
            self.audit.log(username, "登录", "账号已锁定", f"连续失败 5 次，锁定至 {locked}")
            raise ValueError(f"密码连续错误 5 次，账号已锁定至 {locked}")
        self.audit.log(username, "登录", "登录失败")
        raise ValueError("用户名或密码错误，或账号已停用")

    # ---------- 自助注册 ----------

    def register(self, username: str, password: str, activation_code: str) -> int:
        """自助注册：需激活码（固定值），新账号默认【工程师】角色。"""
        username = self._check_username(username)
        if not hmac.compare_digest(activation_code.strip(), ACTIVATION_CODE):
            self.audit.log(username, "注册", "注册失败", "激活码错误")
            raise ValueError("激活码不正确，请联系管理员获取")
        if self.users.get_by_username(username):
            raise ValueError(f"用户名 {username} 已存在，请直接登录或换一个名字")
        self._validate_password(password)
        user_id = self.users.create(username, password, "工程师", operator="自助注册")
        self.audit.log(username, "注册", "注册成功", "新账号（工程师）")
        return user_id

    def change_password(self, user_id: int, old_password: str, new_password: str) -> None:
        user = self.users.get(user_id)
        if not user or not self.users.verify_login(user["username"], old_password):
            raise ValueError("原密码不正确")
        self._validate_password(new_password)
        self.users.set_password(user_id, new_password)
        self.audit.log(user["username"], "用户管理", "修改密码")

    def reset_password(self, operator: str, user_id: int, new_password: str) -> None:
        self._require_admin(operator)
        self._validate_password(new_password)
        user = self.users.get(user_id)
        self.users.set_password(user_id, new_password)
        self.audit.log(operator, "用户管理", "重置密码", f"用户：{user['username'] if user else user_id}")

    def create_user(self, operator: str, username: str, password: str, role: str) -> int:
        self._require_admin(operator)
        username = self._check_username(username)
        if self.users.get_by_username(username):
            raise ValueError(f"用户名 {username} 已存在")
        self._validate_password(password)
        user_id = self.users.create(username, password, role, operator)
        self.audit.log(operator, "用户管理", "新增用户", f"{username}（{role}）")
        return user_id

    def set_role(self, operator: str, user_id: int, role: str) -> None:
        self._require_admin(operator)
        user = self.users.get(user_id)
        if user and user["id"] == self.users.get_by_username(operator)["id"] and role != "管理员":
            raise ValueError("不能降级自己当前登录的管理员账号")
        self.users.set_role(user_id, role)
        self.audit.log(operator, "用户管理", "修改角色", f"{user['username'] if user else user_id} → {role}")

    def set_active(self, operator: str, user_id: int, active: bool) -> None:
        self._require_admin(operator)
        user = self.users.get(user_id)
        if user and user["username"] == operator and not active:
            raise ValueError("不能停用自己的账号")
        self.users.set_active(user_id, active)
        self.audit.log(operator, "用户管理", "停用/启用", f"{user['username'] if user else user_id} → {'启用' if active else '停用'}")

    # ---------- 账号管理（管理员最高权限） ----------

    def reveal_password(self, operator: str, user_id: int) -> str:
        """查看指定账号的密码（明文）。仅管理员；每次查看都记审计日志。"""
        self._require_admin(operator)
        user = self.users.get(user_id)
        if not user:
            raise ValueError("账号不存在")
        password = self.users.reveal_password(user_id)
        self.audit.log(operator, "用户管理", "查看密码", f"用户：{user['username']}")
        if password is None:
            raise ValueError(
                f"账号 {user['username']} 创建于旧版本、未存储可查看的密码副本，请先【重置密码】"
            )
        return password

    def delete_user(self, operator: str, user_id: int) -> None:
        """删除账号。仅管理员。保护规则：不能删自己；系统至少保留一个启用的管理员。"""
        self._require_admin(operator)
        user = self.users.get(user_id)
        if not user:
            raise ValueError("账号不存在")
        username = user["username"]
        if username == operator:
            raise ValueError("不能删除自己当前登录的账号")
        if user["role"] == "管理员":
            other_admins = [
                u for u in self.users.list_all()
                if u["id"] != user_id and u["role"] == "管理员" and u["active"]
            ]
            if not other_admins:
                raise ValueError("系统至少需要保留一个启用的管理员账号，无法删除")
        self.users.delete(user_id)
        self.audit.log(operator, "用户管理", "删除账号", username)

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 6:
            raise ValueError("密码长度至少 6 位")
