"""针卡与数据更新记录的业务规则（校验 + 审计）。

录入边界（防极端/恶意数据污染预测）：
- 累计测试量：0 ~ 1e12 次（一万亿），必须可转为有限数值；
- 针长：0 ~ 2000 um；
- 日期：必须是合法的 YYYY-MM-DD；
- 名称 ≤ 64 字符、备注 ≤ 500 字符。
"""

from __future__ import annotations

import math

from app.repositories.audit_repo import AuditRepo
from app.repositories.cards_repo import CardsRepo
from app.repositories.products_repo import ProductsRepo
from app.repositories.settings_repo import SettingsRepo
from app.repositories.users_repo import UsersRepo
from app.utils import timeutil

MAX_NAME_LEN = 64
MAX_NOTE_LEN = 500
MAX_CUM_TOUCHES = 1e12
MAX_NEEDLE_LEN = 2000.0


class CardService:
    def __init__(
        self,
        cards_repo: CardsRepo,
        products_repo: ProductsRepo,
        audit_repo: AuditRepo,
        settings_repo: SettingsRepo,
        users_repo: UsersRepo,
    ):
        self.cards = cards_repo
        self.products = products_repo
        self.audit = audit_repo
        self.settings = settings_repo
        self.users = users_repo

    def _require_admin(self, operator: str) -> None:
        u = self.users.get_by_username(operator.strip())
        if not u or not u["active"] or u["role"] != "管理员":
            self.audit.log(operator, "针卡台账", "越权尝试", "非管理员调用删除针卡接口")
            raise ValueError("删除针卡需要管理员权限")

    # ---------- 卡片 CRUD ----------

    def create_card(
        self,
        operator: str,
        name: str,
        product_ids: list[int],
        status: str = "在库",
        rated_touches: float = 0.0,
        in_stock_date: str | None = None,
        note: str = "",
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("针卡名称不能为空")
        if len(name) > MAX_NAME_LEN:
            raise ValueError(f"针卡名称过长（最多 {MAX_NAME_LEN} 个字符）")
        if len(note) > MAX_NOTE_LEN:
            raise ValueError(f"备注过长（最多 {MAX_NOTE_LEN} 个字符）")
        if self.cards.get_by_name(name):
            raise ValueError(f"针卡名称 {name} 已存在（名称全库唯一）")
        if not product_ids:
            raise ValueError("请至少勾选一个支持的测试产品")
        try:
            timeutil.parse_date(in_stock_date or timeutil.today_str())
        except ValueError:
            raise ValueError("入库日期格式无效（应为 YYYY-MM-DD）")
        card_id = self.cards.create(
            {
                "name": name,
                "status": status,
                "product_ids": product_ids,
                "rated_touches": rated_touches,
                "in_stock_date": in_stock_date or timeutil.today_str(),
                "note": note,
            }
        )
        pnames = "、".join(self.products.get(pid)["name"] for pid in product_ids)
        self.audit.log(operator, "针卡台账", "新卡入库", f"{name}（{pnames}，{status}）")
        return card_id

    def update_card(
        self,
        operator: str,
        card_id: int,
        name: str,
        product_ids: list[int],
        rated_touches: float = 0.0,
        note: str = "",
    ) -> None:
        name = name.strip()
        if not name:
            raise ValueError("针卡名称不能为空")
        if len(name) > MAX_NAME_LEN:
            raise ValueError(f"针卡名称过长（最多 {MAX_NAME_LEN} 个字符）")
        if len(note) > MAX_NOTE_LEN:
            raise ValueError(f"备注过长（最多 {MAX_NOTE_LEN} 个字符）")
        existing = self.cards.get_by_name(name)
        if existing and existing["id"] != card_id:
            raise ValueError(f"针卡名称 {name} 已被其他卡片使用")
        if not product_ids:
            raise ValueError("请至少勾选一个支持的测试产品")
        self.cards.update(card_id, {
            "name": name, "product_ids": product_ids,
            "rated_touches": rated_touches, "note": note,
        })
        self.audit.log(operator, "针卡台账", "修改信息", name)

    def delete_card(self, operator: str, card_id: int) -> None:
        """仅管理员；连同更新记录一起删除。"""
        self._require_admin(operator)
        card = self.cards.get(card_id)
        if not card:
            return
        self.cards.delete(card_id)
        self.audit.log(operator, "针卡台账", "删除针卡", card["name"])

    # ---------- 数据更新 ----------

    def add_update(
        self,
        operator: str,
        card_id: int,
        update_date: str,
        cum_touches: float,
        needle_len: float,
        note: str = "",
    ) -> list[str]:
        """录入一次（累计测试量, 针长）数据点。返回"软警告"列表（不阻断录入）。"""
        card = self.cards.get(card_id)
        if not card:
            raise ValueError("针卡不存在")
        try:
            timeutil.parse_date(update_date)
        except ValueError:
            raise ValueError("数据日期格式无效（应为 YYYY-MM-DD）")
        if not (math.isfinite(cum_touches) and math.isfinite(needle_len)):
            raise ValueError("测试量/针长必须是有限数值")
        if not (0 <= cum_touches <= MAX_CUM_TOUCHES):
            raise ValueError(f"累计测试量超出合理范围（0 ~ {MAX_CUM_TOUCHES:,.0f} 次）")
        if not (0 < needle_len <= MAX_NEEDLE_LEN):
            raise ValueError(f"针长超出合理范围（0 ~ {MAX_NEEDLE_LEN:g} um）")
        if len(note) > MAX_NOTE_LEN:
            raise ValueError(f"备注过长（最多 {MAX_NOTE_LEN} 个字符）")
        warnings: list[str] = []

        latest = self.cards.latest_update(card_id)
        if latest and cum_touches < float(latest["cum_touches"]):
            warnings.append(
                f"录入的累计测试量小于该卡最近记录（{latest['cum_touches']:.0f}），"
                "请确认为修正数据而非误输入"
            )
        if latest and update_date < latest["update_date"]:
            warnings.append(f"录入日期早于最近一次记录（{latest['update_date']}）")

        scrap_len = self.settings.get_float("scrap_needle_len_um", 22.0)
        if needle_len <= scrap_len:
            warnings.append(f"针长已不高于报废线 {scrap_len:g}um，建议安排报废")
        pids = self.cards.product_ids_of_card(card_id)
        for pid in pids:
            p = self.products.get(pid)
            if p and p["initial_len_um"] and needle_len > float(p["initial_len_um"]) * 1.05:
                warnings.append(f"针长高于产品 {p['name']} 初始针长 {p['initial_len_um']:g}um，请核对单位")
                break

        self.cards.add_update(card_id, update_date, cum_touches, needle_len, operator, note)
        self.audit.log(
            operator, "数据更新", "录入数据",
            f"{card['name']}：累计 {cum_touches:.0f} 次，针长 {needle_len:g}um",
        )
        return warnings

    def delete_update(self, operator: str, update_id: int, card_name: str) -> None:
        self.cards.delete_update(update_id)
        self.audit.log(operator, "数据更新", "删除数据点", f"{card_name} 记录 #{update_id}")
