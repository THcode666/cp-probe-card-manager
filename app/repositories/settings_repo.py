"""全局配置（settings 表）数据访问。

安全：所有数值型参数带取值范围校验（防止把报废线改成 -5、达成率阈值改成 1e9
之类的极端值污染预测与预警）。
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from app.constants import DEFAULT_SETTINGS
from app.database.connection import Database
from app.utils import timeutil

# 参数取值范围（闭区间）；不在表中的键按普通字符串处理（如激活码）
SETTING_BOUNDS: dict[str, tuple[float, float]] = {
    "scrap_needle_len_um": (0.1, 10000),
    "rated_touches_default": (1, 1e12),
    "warn_yellow_pct": (0, 100),
    "warn_red_pct": (0, 100),
    "scrap_remind_days": (0, 365),
    "purchase_buffer_days": (0, 365),
    "min_cards_per_product": (0, 99),
    "demand_horizon_days": (1, 365),
    "min_points_for_own_fit": (2, 1000),
    "backup_keep_days": (7, 3650),
    "default_wph": (0, 10000),
}


class SettingsRepo:
    def __init__(self, db: Database):
        self.db = db
        # 版本号：配置修改 +1，供预测/需求缓存失效判断
        self.data_version = 0

    def _bump(self) -> None:
        self.data_version += 1

    def ensure_defaults(self) -> None:
        """首次建库时写入出厂默认值（已存在的键不覆盖，保留工程师改过的值）；
        并迁移清理已废弃的键（register_activation_code 已改为代码内固定值）。"""
        def _do(con: sqlite3.Connection) -> None:
            for key, value in DEFAULT_SETTINGS.items():
                con.execute(
                    "INSERT OR IGNORE INTO settings (key, value, description, updated_at, updated_by) "
                    "VALUES (?, ?, ?, NULL, NULL)",
                    (key, value, ""),
                )
            con.execute("DELETE FROM settings WHERE key = 'register_activation_code'")
        self.db.transaction(_do)

    def all(self) -> dict[str, dict]:
        rows = self.db.query("SELECT key, value, description, updated_at, updated_by FROM settings ORDER BY key")
        return {r["key"]: dict(r) for r in rows}

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def get_float(self, key: str, default: float = 0.0) -> float:
        raw = self.get(key)
        try:
            return float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        return int(self.get_float(key, float(default)))

    def set(self, key: str, value: str, operator: str) -> None:
        if key not in SETTING_BOUNDS:
            raise ValueError(f"未知参数：{key}")
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"参数 {key} 必须是数字")
        lo, hi = SETTING_BOUNDS[key]
        if not (lo <= num <= hi):
            raise ValueError(f"参数 {key} 取值须在 {lo:g} ~ {hi:g} 之间，当前输入：{value}")
        self.db.execute(
            "UPDATE settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = ?",
            (value, timeutil.now_str(), operator, key),
        )
        self._bump()
