"""仓库流转服务：领用上机 / 下机回库 / 报废，以及仓库统计。"""

from __future__ import annotations

import sqlite3

from app.constants import CardStatus
from app.repositories.audit_repo import AuditRepo
from app.repositories.cards_repo import CardsRepo


class WarehouseService:
    def __init__(self, cards_repo: CardsRepo, audit_repo: AuditRepo):
        self.cards = cards_repo
        self.audit = audit_repo

    # ---------- 流转 ----------

    def take_to_machine(self, operator: str, card_id: int) -> None:
        """领用上机：在库 → 在用。"""
        card = self._require(card_id)
        if card["status"] != CardStatus.IN_STOCK:
            raise ValueError(f"仅【在库】的针卡可以领用上机（当前：{card['status']}）")
        self.cards.set_status(card_id, CardStatus.IN_USE, operator, module="仓库")

    def return_to_stock(self, operator: str, card_id: int) -> None:
        """下机回库：在用 → 在库。"""
        card = self._require(card_id)
        if card["status"] != CardStatus.IN_USE:
            raise ValueError(f"仅【在用】的针卡可以下机回库（当前：{card['status']}）")
        self.cards.set_status(card_id, CardStatus.IN_STOCK, operator, module="仓库")

    def scrap(self, operator: str, card_id: int) -> None:
        """报废：任意状态 → 报废（界面需二次确认）。"""
        card = self._require(card_id)
        if card["status"] == CardStatus.SCRAPPED:
            raise ValueError("该针卡已经是报废状态")
        self.cards.set_status(card_id, CardStatus.SCRAPPED, operator, module="仓库")

    def _require(self, card_id: int) -> sqlite3.Row:
        card = self.cards.get(card_id)
        if not card:
            raise ValueError("针卡不存在")
        return card

    # ---------- 统计 ----------

    def status_counts(self) -> dict[str, int]:
        rows = self.cards.list_cards()
        counts = {s.value: 0 for s in CardStatus}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        return counts

    def stock_count_by_product(self) -> dict[int, int]:
        """每个产品名下的【在库】卡数（兼容多产品：一张在库卡为它的每个产品 +1）。"""
        rows = self.cards.list_cards(status=CardStatus.IN_STOCK)
        counts: dict[int, int] = {}
        for r in rows:
            for pid in self.cards.product_ids_of_card(r["id"]):
                counts[pid] = counts.get(pid, 0) + 1
        return counts
