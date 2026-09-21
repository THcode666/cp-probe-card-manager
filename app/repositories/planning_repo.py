"""站点与 WIP 数据访问。"""

from __future__ import annotations

from typing import Optional

from app.database.connection import Database
from app.utils import timeutil


class PlanningRepo:
    def __init__(self, db: Database):
        self.db = db

    # ---------- 站点 ----------

    def list_stations(self, include_inactive: bool = False, stage: Optional[str] = None) -> list:
        sql = "SELECT * FROM stations"
        where: list[str] = []
        params: list = []
        if not include_inactive:
            where.append("active = 1")
        if stage:
            where.append("stage = ?")
            params.append(stage)
        if where:
            sql += " WHERE " + " AND ".join(where)
        # N2 站点按到 CP 时间升序（即距离 CP 的先后顺序），N1 按名称
        sql += " ORDER BY stage DESC, CASE WHEN stage='N2' THEN days_to_cp ELSE 999999 END, name"
        return self.db.query(sql, tuple(params))

    def get_station(self, station_id: int) -> Optional[dict]:
        row = self.db.query_one("SELECT * FROM stations WHERE id = ?", (station_id,))
        return dict(row) if row else None

    def create_station(self, name: str, days_to_cp: float, stage: str = "N2") -> int:
        name = name.strip()
        if not name:
            raise ValueError("站点名称不能为空")
        if len(name) > 64:
            raise ValueError("站点名称过长（最多 64 个字符）")
        if self.db.query_one("SELECT 1 FROM stations WHERE name = ?", (name,)):
            raise ValueError(f"站点 {name} 已存在")
        return self.db.execute(
            "INSERT INTO stations (name, days_to_cp, stage, active) VALUES (?, ?, ?, 1)",
            (name, days_to_cp, stage),
        )

    def update_station(
        self, station_id: int, name: str, days_to_cp: float, active: bool = True, stage: str = "N2"
    ) -> None:
        self.db.execute(
            "UPDATE stations SET name = ?, days_to_cp = ?, active = ?, stage = ? WHERE id = ?",
            (name, days_to_cp, 1 if active else 0, stage, station_id),
        )

    def delete_station(self, station_id: int) -> None:
        """彻底删除站点；其下 WIP 记录随外键级联删除（连接已开启外键）。"""
        self.db.execute("DELETE FROM stations WHERE id = ?", (station_id,))

    # ---------- WIP ----------

    def list_wip(self, product_id: Optional[int] = None) -> list:
        """WIP 记录（带产品名/站点名便于展示与导出）。"""
        sql = (
            "SELECT w.*, p.name AS product_name, s.name AS station_name, s.days_to_cp "
            "FROM wip w JOIN products p ON p.id = w.product_id "
            "JOIN stations s ON s.id = w.station_id"
        )
        params: tuple = ()
        if product_id:
            sql += " WHERE w.product_id = ?"
            params = (product_id,)
        return self.db.query(sql + " ORDER BY p.name, s.days_to_cp", params)

    def wip_matrix(self) -> dict[int, dict[int, int]]:
        """{product_id: {station_id: qty}}"""
        rows = self.db.query("SELECT product_id, station_id, qty FROM wip WHERE qty > 0")
        matrix: dict[int, dict[int, int]] = {}
        for r in rows:
            matrix.setdefault(r["product_id"], {})[r["station_id"]] = r["qty"]
        return matrix

    def set_wip(self, product_id: int, station_id: int, qty: int, operator: str) -> None:
        if not isinstance(qty, int) or not (0 <= qty <= 1_000_000_000):
            raise ValueError("WIP 片数须为 0 ~ 1,000,000,000 的整数")
        self.db.execute(
            "INSERT INTO wip (product_id, station_id, qty, updated_at, updated_by) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (product_id, station_id) "
            "DO UPDATE SET qty = excluded.qty, updated_at = excluded.updated_at, updated_by = excluded.updated_by",
            (product_id, station_id, qty, timeutil.now_str(), operator),
        )
