"""针卡、针卡-产品关联、针卡数据更新记录 三者的数据访问。"""

from __future__ import annotations

import sqlite3
from typing import Optional

from app.database.connection import Database
from app.utils import timeutil

# 列表页联查：每张卡带上支持的产品名、最近一次更新（累计测试量/针长/日期）
_CARD_LIST_SQL = """
SELECT c.*,
       (SELECT GROUP_CONCAT(p.name, ', ')
          FROM card_products cp JOIN products p ON p.id = cp.product_id
         WHERE cp.card_id = c.id) AS product_names,
       lu.cum_touches AS last_touches,
       lu.needle_len  AS last_len,
       lu.update_date AS last_update_date
FROM cards c
LEFT JOIN (SELECT card_id, MAX(id) AS mid FROM card_updates GROUP BY card_id) m ON m.card_id = c.id
LEFT JOIN card_updates lu ON lu.id = m.mid
"""


class CardsRepo:
    def __init__(self, db: Database):
        self.db = db
        # 本进程内"针卡相关数据"的版本号：任何写操作 +1。
        # 供预测/需求缓存做失效判断（配合 Database.data_version 感知其他客户端的修改）。
        self.data_version = 0

    def _bump(self) -> None:
        self.data_version += 1

    # ---------- 卡片 ----------

    def list_cards(
        self,
        status: Optional[str] = None,
        product_id: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> list[sqlite3.Row]:
        sql, params = _CARD_LIST_SQL, []
        where: list[str] = []
        if status:
            where.append("c.status = ?")
            params.append(status)
        if product_id:
            where.append(
                "c.id IN (SELECT card_id FROM card_products WHERE product_id = ?)"
            )
            params.append(product_id)
        if keyword:
            where.append("c.name LIKE ?")
            params.append(f"%{keyword}%")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY c.name"
        return self.db.query(sql, tuple(params))

    def get(self, card_id: int) -> Optional[sqlite3.Row]:
        return self.db.query_one("SELECT * FROM cards WHERE id = ?", (card_id,))

    def get_by_name(self, name: str) -> Optional[sqlite3.Row]:
        return self.db.query_one("SELECT * FROM cards WHERE name = ?", (name,))

    def create(self, data: dict) -> int:
        def _do(con: sqlite3.Connection) -> int:
            cur = con.execute(
                "INSERT INTO cards (name, status, rated_touches, in_stock_date, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    data["name"],
                    data.get("status", "在库"),
                    data.get("rated_touches", 0),
                    data.get("in_stock_date") or timeutil.today_str(),
                    data.get("note", ""),
                    timeutil.now_str(),
                ),
            )
            card_id = int(cur.lastrowid)
            for pid in data.get("product_ids", []):
                con.execute(
                    "INSERT OR IGNORE INTO card_products (card_id, product_id) VALUES (?, ?)",
                    (card_id, pid),
                )
            return card_id
        self._bump()
        return self.db.transaction(_do)  # type: ignore[return-value]

    def update(self, card_id: int, data: dict) -> None:
        def _do(con: sqlite3.Connection) -> None:
            con.execute(
                "UPDATE cards SET name = ?, rated_touches = ?, note = ? WHERE id = ?",
                (data["name"], data.get("rated_touches", 0), data.get("note", ""), card_id),
            )
            if "product_ids" in data:
                con.execute("DELETE FROM card_products WHERE card_id = ?", (card_id,))
                for pid in data["product_ids"]:
                    con.execute(
                        "INSERT OR IGNORE INTO card_products (card_id, product_id) VALUES (?, ?)",
                        (card_id, pid),
                    )
        self.db.transaction(_do)
        self._bump()

    def set_status(self, card_id: int, status: str, operator: str, module: str = "仓库") -> None:
        """状态流转并自动记日志、报废时记报废日期。"""
        def _do(con: sqlite3.Connection) -> None:
            row = con.execute("SELECT status FROM cards WHERE id = ?", (card_id,)).fetchone()
            old = row["status"] if row else ""
            if status == "报废":
                con.execute(
                    "UPDATE cards SET status = ?, scrapped_date = ? WHERE id = ?",
                    (status, timeutil.today_str(), card_id),
                )
            else:
                con.execute("UPDATE cards SET status = ? WHERE id = ?", (status, card_id))
            con.execute(
                "INSERT INTO audit_log (ts, operator, module, action, detail) VALUES (?, ?, ?, ?, ?)",
                (
                    timeutil.now_str(),
                    operator,
                    module,
                    "状态流转",
                    f"{old} → {status}",
                ),
            )
        self.db.transaction(_do)
        self._bump()

    def delete(self, card_id: int) -> None:
        self.db.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        self._bump()

    def product_ids_of_card(self, card_id: int) -> list[int]:
        rows = self.db.query(
            "SELECT product_id FROM card_products WHERE card_id = ? ORDER BY product_id", (card_id,)
        )
        return [r["product_id"] for r in rows]

    def count_by_product(self, status: Optional[str] = None) -> dict[int, int]:
        """{product_id: 卡数}，单条 SQL 分组完成（替代逐卡 N+1 查询）。"""
        sql = ("SELECT cp.product_id AS pid, COUNT(*) AS n "
               "FROM card_products cp JOIN cards c ON c.id = cp.card_id ")
        params: tuple = ()
        if status:
            sql += "WHERE c.status = ? "
            params = (status,)
        sql += "GROUP BY cp.product_id"
        return {r["pid"]: r["n"] for r in self.db.query(sql, params)}

    # ---------- 更新记录 ----------

    def add_update(
        self,
        card_id: int,
        update_date: str,
        cum_touches: float,
        needle_len: float,
        operator: str,
        note: str = "",
    ) -> int:
        new_id = self.db.execute(
            "INSERT INTO card_updates (card_id, update_date, cum_touches, needle_len, operator, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (card_id, update_date, cum_touches, needle_len, operator, note, timeutil.now_str()),
        )
        self._bump()
        return new_id

    def updates_for_card(self, card_id: int) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT * FROM card_updates WHERE card_id = ? ORDER BY update_date, id", (card_id,)
        )

    def latest_update(self, card_id: int) -> Optional[sqlite3.Row]:
        return self.db.query_one(
            "SELECT * FROM card_updates WHERE card_id = ? ORDER BY cum_touches DESC, update_date DESC, id DESC LIMIT 1",
            (card_id,),
        )

    def delete_update(self, update_id: int) -> None:
        self.db.execute("DELETE FROM card_updates WHERE id = ?", (update_id,))
        self._bump()

    def update_points_for_product(self, product_id: int) -> list[sqlite3.Row]:
        """某产品全部针卡（含已报废，报废卡的完整寿命对拟合最宝贵）的磨损数据点。"""
        return self.db.query(
            "SELECT cu.card_id, cu.cum_touches, cu.needle_len "
            "FROM card_updates cu "
            "JOIN card_products cp ON cp.card_id = cu.card_id "
            "WHERE cp.product_id = ? "
            "ORDER BY cu.cum_touches",
            (product_id,),
        )

    def update_points_for_card(self, card_id: int) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT cum_touches, needle_len, update_date FROM card_updates "
            "WHERE card_id = ? ORDER BY cum_touches",
            (card_id,),
        )
