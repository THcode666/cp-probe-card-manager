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

    def list_recent(
        self,
        limit: int = 300,
        keyword: Optional[str] = None,
        module: Optional[str] = None,
    ) -> list:
        """最近日志。keyword 模糊匹配操作人/模块/动作/详情；module 精确筛选模块。"""
        sql = "SELECT * FROM audit_log"
        where: list[str] = []
        params: list = []
        if module:
            where.append("module = ?")
            params.append(module)
        if keyword:
            where.append("(operator LIKE ? OR module LIKE ? OR action LIKE ? OR detail LIKE ?)")
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw, kw])
        if where:
            sql += " WHERE " + " AND ".join(where)
        return self.db.query(sql + " ORDER BY id DESC LIMIT ?", (*params, limit))

    def list_modules(self) -> list[str]:
        """日志中出现过的全部模块名（供筛选下拉用，含顺序无关的历史模块）。"""
        rows = self.db.query("SELECT DISTINCT module FROM audit_log ORDER BY module")
        return [r["module"] for r in rows]
