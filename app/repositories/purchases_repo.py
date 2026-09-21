"""采购单数据访问。"""

from __future__ import annotations

from typing import Optional

from app.database.connection import Database
from app.utils import timeutil


class PurchasesRepo:
    def __init__(self, db: Database):
        self.db = db

    def list_all(self, status: Optional[str] = None) -> list:
        sql = (
            "SELECT pu.*, p.name AS product_name FROM purchases pu "
            "JOIN products p ON p.id = pu.product_id"
        )
        params: tuple = ()
        if status:
            sql += " WHERE pu.status = ?"
            params = (status,)
        return self.db.query(sql + " ORDER BY pu.order_date DESC, pu.id DESC")

    def create(self, product_id: int, qty: int, order_date: str, eta_date: str, operator: str, note: str = "") -> int:
        return self.db.execute(
            "INSERT INTO purchases (product_id, qty, order_date, eta_date, status, operator, note, created_at) "
            "VALUES (?, ?, ?, ?, '已下单', ?, ?, ?)",
            (product_id, qty, order_date, eta_date, operator, note, timeutil.now_str()),
        )

    def set_status(self, purchase_id: int, status: str) -> None:
        self.db.execute("UPDATE purchases SET status = ? WHERE id = ?", (status, purchase_id))

    def delete(self, purchase_id: int) -> None:
        """删除采购单（任意状态）。删除后该单不再计入在途数量。"""
        self.db.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))

    def in_transit_qty(self, product_id: int) -> int:
        """在途数量：已下单未到货、未取消。"""
        row = self.db.query_one(
            "SELECT COALESCE(SUM(qty), 0) AS total FROM purchases "
            "WHERE product_id = ? AND status = '已下单'",
            (product_id,),
        )
        return int(row["total"]) if row else 0
