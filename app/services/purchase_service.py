"""采购预估服务：预测缺口出现日 → 倒推最晚下单日 → 分级预警与建议数量。

判定口径：
- 缺口日：展望期内累计测试量需求首次超过"现有可用卡剩余寿命合计"的那一天；
- 最晚下单日 = 缺口日 − 采购提前期（产品配置）− 采购缓冲天数（全局配置）；
- 最晚下单日已过 → 立即下单（红）；7 天内 → 尽快下单（黄）；展望期内无缺口 → 暂不需要；
- 建议数量 = 需求缺口折算张数 + 三卡规则缺口 − 在途采购数量（下限 0）。
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass

from app.constants import AlertLevel
from app.repositories.products_repo import ProductsRepo
from app.repositories.purchases_repo import PurchasesRepo
from app.repositories.settings_repo import SettingsRepo
from app.services.demand_service import DemandService
from app.services.prediction_service import PredictionService


@dataclass
class PurchaseAdvice:
    product_id: int
    product_name: str
    stock_cards: int = 0                # 在库卡数（三卡规则口径）
    three_card_gap: int = 0
    in_transit: int = 0
    horizon_days: int = 14
    total_touches_needed: float = 0.0
    capacity_touches: float = 0.0
    shortage_day: int | None = None     # 展望期内第几天出现缺口（None=无缺口）
    shortage_date: str | None = None
    deadline_date: str | None = None    # 最晚下单日
    urgency: str = AlertLevel.UNKNOWN   # AlertLevel.OK / YELLOW / RED / UNKNOWN
    urgency_text: str = "数据不足"
    suggested_qty: int = 0
    lead_time_days: float = 0.0
    avg_card_life: float = 0.0          # 用于折算的单卡可用寿命


class PurchaseService:
    def __init__(
        self,
        products_repo: ProductsRepo,
        purchases_repo: PurchasesRepo,
        demand: DemandService,
        prediction: PredictionService,
        settings_repo: SettingsRepo,
    ):
        self.products = products_repo
        self.purchases = purchases_repo
        self.demand = demand
        self.prediction = prediction
        self.settings = settings_repo

    @property
    def buffer_days(self) -> float:
        return self.settings.get_float("purchase_buffer_days", 7.0)

    def advise_for_product(self, product_id: int) -> PurchaseAdvice:
        p = self.products.get(product_id)
        advice = PurchaseAdvice(
            product_id=product_id, product_name=p["name"] if p else "?"
        )
        if not p:
            return advice
        advice.lead_time_days = float(p["lead_time_days"] or 0)

        d = self.demand.compute_for_product(product_id)
        advice.stock_cards = d.stock_cards
        advice.three_card_gap = d.three_card_gap
        advice.in_transit = self.purchases.in_transit_qty(product_id)
        advice.horizon_days = d.horizon_days
        advice.total_touches_needed = d.total_touches
        advice.capacity_touches = d.capacity_touches

        # 单卡可用寿命：优先用该产品卡的预测报废测试量均值，退化用额定值
        preds = [
            self.prediction.predict_card(r["id"])
            for r in self.demand.cards_for_product(product_id)
            if r["status"] != "报废"
        ]
        scrap_touches = [x.touches_at_scrap for x in preds if x.touches_at_scrap]
        advice.avg_card_life = (
            sum(scrap_touches) / len(scrap_touches) if scrap_touches
            else (d.avg_remaining or (float(p["rated_touches"]) or self.prediction.default_rated))
        )

        # 缺口日：累计需求首次超过现有总余量的天
        cum = 0.0
        per_day_touches = {
            day: q * d.touches_per_wafer for day, q in d.arrivals_by_day.items()
        }
        for day in range(d.horizon_days + 1):
            cum += per_day_touches.get(day, 0.0)
            if cum > d.capacity_touches and cum > 0:
                advice.shortage_day = day
                break

        today = _dt.date.today()
        if advice.shortage_day is None:
            # 展望期内无缺口，但三卡规则缺口仍需考虑采购
            advice.urgency = AlertLevel.OK
            advice.urgency_text = "展望期内无缺口"
        else:
            advice.shortage_date = (today + _dt.timedelta(days=advice.shortage_day)).isoformat()
            deadline = today + _dt.timedelta(
                days=round(advice.shortage_day - advice.lead_time_days - self.buffer_days)
            )
            advice.deadline_date = deadline.isoformat()
            offset = (deadline - today).days
            if offset < 0:
                advice.urgency = AlertLevel.RED
                advice.urgency_text = "已过最晚下单日，请立即下单"
            elif offset <= 7:
                advice.urgency = AlertLevel.YELLOW
                advice.urgency_text = f"请在 {offset + 1} 天内下单"
            else:
                advice.urgency = AlertLevel.OK
                advice.urgency_text = "暂不需要下单"

        # 建议数量：测试量缺口折算 + 三卡缺口 − 在途
        deficit_touches = max(0.0, d.total_touches - d.capacity_touches)
        qty = 0
        if advice.avg_card_life > 0:
            qty = math.ceil(deficit_touches / advice.avg_card_life)
        qty += advice.three_card_gap
        qty = max(0, qty - advice.in_transit)
        # 即便展望期内测试量无缺口，三卡缺口也提示补足
        advice.suggested_qty = qty
        if advice.shortage_day is None and advice.suggested_qty == 0 and advice.three_card_gap == 0:
            advice.urgency_text = "展望期内无缺口"
        return advice

    def advise_all(self) -> list[PurchaseAdvice]:
        return [self.advise_for_product(p["id"]) for p in self.products.list_all()]
