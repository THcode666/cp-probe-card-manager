"""操作日志数据访问。"""

from __future__ import annotations

from typing import Optional

from app.database.connection import Database
from app.utils import timeutil


class AuditRepo:
    def __init__(self, db: Database):
        self.db = db

    def log(self, operator: str, module: str, action: str, detail: str = "") -> None:
        self.db.execute(
            "INSERT INTO audit_log (ts, operator, module, action, detail) VALUES (?, ?, ?, ?, ?)",
            (timeutil.now_str(), operator, module, action, detail),
        )

    def list_recent(self, limit: int = 300, keyword: Optional[str] = None) -> list:
        sql = "SELECT * FROM audit_log"
        params: tuple = ()
        if keyword:
            sql += " WHERE operator LIKE ? OR module LIKE ? OR action LIKE ? OR detail LIKE ?"
            kw = f"%{keyword}%"
            params = (kw, kw, kw, kw)
        return self.db.query(sql + " ORDER BY id DESC LIMIT ?", (*params, limit))
