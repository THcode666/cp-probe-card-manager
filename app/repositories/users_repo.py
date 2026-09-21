"""用户数据访问。

密码双存储：
- password_hash：PBKDF2-SHA256 不可逆哈希，用于登录校验（标准做法）；
- password_recover：可逆混淆副本（XOR + base64），仅供管理员"查看密码"功能使用。
  注意：这使数据库文件本身可以还原出明文密码，请把 db 文件放在受控的共享目录，
  并不要把 db 或备份发给不可信的人。不需要该功能时可在系统设置侧放弃使用。

登录防暴力破解：连续失败 5 次锁定账号 5 分钟（failed_attempts / locked_until 列）。
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import secrets
import sqlite3
from typing import Optional

from app.database.connection import Database
from app.utils import timeutil

_ITERATIONS = 100_000
_XOR_KEY = b"CP-PCMS-RECOVER-2026"
LOGIN_MAX_FAILURES = 5      # 连续失败次数上限
LOGIN_LOCK_MINUTES = 5      # 锁定时长（分钟）

# 内置账号（首次建库时创建，已存在则跳过、不覆盖用户改过的密码）
BUILTIN_ACCOUNTS: list[tuple[str, str, str]] = [
    # 演示默认账号：公开仓库使用占位密码，部署时请改成自己的初始密码，
    # 并在首次登录后立即修改（软件会主动提醒仍在使用默认密码的账号）。
    ("admin", "Admin@12345", "管理员"),
]


def is_builtin_default(username: str, password: str) -> bool:
    """判断是否仍在使用内置账号的出厂默认密码（用于登录后提醒修改）。"""
    return any(username == u and password == p for u, p, _ in BUILTIN_ACCOUNTS)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    ).hex()


def new_salt() -> str:
    return secrets.token_hex(16)


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected_hash)


def store_recoverable(password: str) -> str:
    data = password.encode("utf-8")
    xored = bytes(b ^ _XOR_KEY[i % len(_XOR_KEY)] for i, b in enumerate(data))
    return base64.b64encode(xored).decode("ascii")


def reveal_recoverable(token: str) -> str:
    data = base64.b64decode(token.encode("ascii"))
    xored = bytes(b ^ _XOR_KEY[i % len(_XOR_KEY)] for i, b in enumerate(data))
    return xored.decode("utf-8")


class UsersRepo:
    def __init__(self, db: Database):
        self.db = db

    def ensure_builtin_accounts(self) -> None:
        """首次使用：内置管理员账号。已存在则跳过（不覆盖用户改过的密码）。"""
        if self.db.query_one("SELECT 1 FROM users LIMIT 1") is None:
            for username, password, role in BUILTIN_ACCOUNTS:
                self.create(username, password, role, operator="system")
            return
        for username, password, role in BUILTIN_ACCOUNTS:
            if self.get_by_username(username) is None:
                self.create(username, password, role, operator="system")

    def create(self, username: str, password: str, role: str, operator: str) -> int:
        salt = new_salt()
        return self.db.execute(
            "INSERT INTO users (username, password_hash, salt, role, active, created_at, password_recover) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)",
            (username, hash_password(password, salt), salt, role, timeutil.now_str(),
             store_recoverable(password)),
        )

    def get_by_username(self, username: str) -> Optional[sqlite3.Row]:
        return self.db.query_one("SELECT * FROM users WHERE username = ?", (username,))

    def get(self, user_id: int) -> Optional[sqlite3.Row]:
        return self.db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))

    def list_all(self) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM users ORDER BY id")

    def verify_login(self, username: str, password: str) -> Optional[sqlite3.Row]:
        user = self.get_by_username(username)
        if user and user["active"] and verify_password(password, user["salt"], user["password_hash"]):
            return user
        return None

    def set_password(self, user_id: int, new_password: str) -> None:
        salt = new_salt()
        self.db.execute(
            "UPDATE users SET password_hash = ?, salt = ?, password_recover = ? WHERE id = ?",
            (hash_password(new_password, salt), salt, store_recoverable(new_password), user_id),
        )

    def reveal_password(self, user_id: int) -> Optional[str]:
        """返回可查看的明文密码；旧版本账号未存副本时返回 None。"""
        user = self.get(user_id)
        if not user or not user["password_recover"]:
            return None
        return reveal_recoverable(user["password_recover"])

    def set_role(self, user_id: int, role: str) -> None:
        self.db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))

    def set_active(self, user_id: int, active: bool) -> None:
        self.db.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))

    def delete(self, user_id: int) -> None:
        self.db.execute("DELETE FROM users WHERE id = ?", (user_id,))

    # ---------- 登录防暴力破解 ----------

    def record_login_failure(self, user_id: int) -> str:
        """累计失败次数；达到上限则锁定账号，返回锁定截止时间（未锁定返回 ''）。"""
        def _do(con: sqlite3.Connection) -> str:
            con.execute(
                "UPDATE users SET failed_attempts = failed_attempts + 1 WHERE id = ?", (user_id,)
            )
            row = con.execute(
                "SELECT failed_attempts FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row and row["failed_attempts"] >= LOGIN_MAX_FAILURES:
                locked_until = (
                    _dt.datetime.now() + _dt.timedelta(minutes=LOGIN_LOCK_MINUTES)
                ).strftime(timeutil.TS_FMT)
                con.execute(
                    "UPDATE users SET locked_until = ?, failed_attempts = 0 WHERE id = ?",
                    (locked_until, user_id),
                )
                return locked_until
            return ""
        return self.db.transaction(_do)  # type: ignore[return-value]

    def record_login_success(self, user_id: int) -> None:
        self.db.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (user_id,)
        )

    def clear_lock_if_expired(self, user_id: int, locked_until: str) -> None:
        """锁定时间已过则解除锁定。"""
        locked_at = _dt.datetime.strptime(locked_until, timeutil.TS_FMT)
        if _dt.datetime.now() >= locked_at:
            self.db.execute(
                "UPDATE users SET locked_until = NULL, failed_attempts = 0 WHERE id = ?", (user_id,)
            )
