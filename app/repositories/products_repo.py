"""产品配置数据访问。"""

from __future__ import annotations

import sqlite3
from typing import Optional

from app.database.connection import Database
from app.utils import timeutil


class ProductsRepo:
    def __init__(self, db: Database):
        self.db = db

    def list_all(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM products"
        if not include_inactive:
            sql += " WHERE active = 1"
        return self.db.query(sql + " ORDER BY name")

    def get(self, product_id: int) -> Optional[sqlite3.Row]:
        return self.db.query_one("SELECT * FROM products WHERE id = ?", (product_id,))

    def get_by_name(self, name: str) -> Optional[sqlite3.Row]:
        return self.db.query_one("SELECT * FROM products WHERE name = ?", (name,))

    @staticmethod
    def _validate(data: dict) -> None:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("产品名称不能为空")
        if len(name) > 64:
            raise ValueError("产品名称过长（最多 64 个字符）")
        if len(data.get("note", "")) > 500:
            raise ValueError("备注过长（最多 500 个字符）")
        for field in ("touches_per_wafer", "wph", "initial_len_um", "rated_touches", "lead_time_days"):
            v = float(data.get(field, 0) or 0)
            if v < 0 or v > 1e12:
                raise ValueError(f"字段 {field} 取值超出合理范围（0 ~ 1e12）")

    def create(self, data: dict) -> int:
        self._validate(data)

        def _do(con: sqlite3.Connection) -> int:
            cur = con.execute(
                "INSERT INTO products (name, touches_per_wafer, wph, initial_len_um, rated_touches, "
                "lead_time_days, note, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    data["name"],
                    data.get("touches_per_wafer", 0),
                    data.get("wph", 0),
                    data.get("initial_len_um", 0),
                    data.get("rated_touches", 0),
                    data.get("lead_time_days", 0),
                    data.get("note", ""),
                    timeutil.now_str(),
                ),
            )
            return int(cur.lastrowid)
        return self.db.transaction(_do)  # type: ignore[return-value]

    def purchase_count(self, product_id: int) -> int:
        """引用该产品的采购单数量（删除前检查）。"""
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM purchases WHERE product_id = ?", (product_id,)
        )
        return int(row["n"]) if row else 0

    def orphan_cards(self, product_id: int) -> list:
        """若删除该产品，将变成"没有任何支持产品"的针卡列表（应先处理）。"""
        return self.db.query(
            "SELECT c.name FROM cards c "
            "WHERE EXISTS (SELECT 1 FROM card_products cp WHERE cp.card_id = c.id AND cp.product_id = ?) "
            "AND NOT EXISTS (SELECT 1 FROM card_products cp2 WHERE cp2.card_id = c.id AND cp2.product_id != ?) "
            "ORDER BY c.name",
            (product_id, product_id),
        )

    def delete(self, product_id: int) -> None:
        """删除产品；card_products 与 wip 随外键级联删除。
        有采购单引用时在数据层强制阻断（孤儿卡校验由界面层提前给出明细）。"""
        count = self.purchase_count(product_id)
        if count:
            raise ValueError(
                f"该产品名下还有 {count} 张采购单，无法删除；请先在【采购管理 → 采购单】中删除或取消。"
            )
        self.db.execute("DELETE FROM products WHERE id = ?", (product_id,))

    def update(self, product_id: int, data: dict) -> None:
        self._validate(data)
        self.db.execute(
            "UPDATE products SET name = ?, touches_per_wafer = ?, wph = ?, initial_len_um = ?, "
            "rated_touches = ?, lead_time_days = ?, note = ?, active = ? WHERE id = ?",
            (
                data["name"],
                data.get("touches_per_wafer", 0),
                data.get("wph", 0),
                data.get("initial_len_um", 0),
                data.get("rated_touches", 0),
                data.get("lead_time_days", 0),
                data.get("note", ""),
                1 if data.get("active", True) else 0,
                product_id,
            ),
        )
