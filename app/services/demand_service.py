"""需求预估服务：WIP → 未来到达片数 → 测试量需求 → 折算针卡需求。

估算口径（与工程师确认的规则一致）：
- 站点 WIP 按其"到 CP 周转天数"推算到达日：arrival_day = round(days_to_cp)；
- 到达片的测试量消耗 = 片数 × 片耗（配置的 touches_per_wafer）；
- 展望期内需求张数 = 总测试量需求 ÷ 单卡平均剩余寿命（向上取整），
  并叠加三卡规则缺口（可用卡不足 min_cards_per_product 的部分）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.constants import AlertLevel
from app.repositories.planning_repo import PlanningRepo
from app.repositories.products_repo import ProductsRepo
from app.repositories.settings_repo import SettingsRepo
from app.services.prediction_service import PredictionService


@dataclass
class ProductDemand:
    product_id: int
    product_name: str
    horizon_days: int = 14
    touches_per_wafer: float = 0.0
    wph: float = 0.0
    arrivals_by_day: dict[int, float] = field(default_factory=dict)  # day_offset -> wafers（N2 站点）
    total_wafers: float = 0.0
    total_touches: float = 0.0
    daily_touches_by_wph: float = 0.0     # 吞吐口径参考：单台机台每天消耗测试量
    n1_wip_total: float = 0.0             # N1 在制片数合计（只计数量，不参与时间推算）
    n1_wip_detail: dict[str, float] = field(default_factory=dict)  # {N1站点: 片数}
    stock_cards: int = 0                  # 在库卡数（三卡规则口径：在用不计入）
    three_card_gap: int = 0               # 三卡规则缺口（按在库数）
    capacity_touches: float = 0.0         # 全部可用卡（在库+在用）剩余寿命合计（产能口径）
    avg_remaining: float = 0.0            # 单卡平均剩余寿命
    cards_needed: int = 0                 # 展望期内需求折算张数（含三卡规则）


class DemandService:
    def __init__(
        self,
        products_repo: ProductsRepo,
        planning_repo: PlanningRepo,
        prediction: PredictionService,
        settings_repo: SettingsRepo,
    ):
        self.products = products_repo
        self.planning = planning_repo
        self.prediction = prediction
        self.settings = settings_repo
        # ---- 性能缓存（重构优化）----
        # compute_for_product 单卡预测借力 PredictionService 缓存；
        # 这里再按版本缓存整个 ProductDemand，主控面板/采购页不再重复推算。
        self._demand_cache: dict[int, tuple[tuple, ProductDemand]] = {}

    def _cache_versions(self) -> tuple:
        return (
            self.products.data_version,
            self.planning.data_version,
            self.settings.data_version,
            self.prediction._cache_versions(),
        )

    @property
    def horizon_days(self) -> int:
        return self.settings.get_int("demand_horizon_days", 14)

    @property
    def min_cards(self) -> int:
        return self.settings.get_int("min_cards_per_product", 3)

    def arrivals_by_day(self, product_id: int, horizon: int) -> dict[int, float]:
        """未来 0..horizon 天每天到达 CP 的片数。

        只统计 **N2 站点**的 WIP（arrival_day = 站点到 CP 周转天数）；
        N1 站点距 CP 时间过长，只计数量、不参与时间推算（见 n1_wip_summary）。
        """
        arrivals: dict[int, float] = {}
        stage_by_station = {
            s["id"]: s["stage"] for s in self.planning.list_stations(include_inactive=True)
        }
        for w in self.planning.list_wip(product_id):
            if w["qty"] <= 0 or stage_by_station.get(w["station_id"]) != "N2":
                continue
            day = int(round(float(w["days_to_cp"])))
            if 0 <= day <= horizon:
                arrivals[day] = arrivals.get(day, 0) + w["qty"]
        return arrivals

    def n1_wip_summary(self, product_id: int) -> tuple[float, dict[str, float]]:
        """N1 在制汇总：(合计片数, {N1站点名: 片数})。只计数量，不参与时间推算。"""
        stage_by_station = {
            s["id"]: s["name"] for s in self.planning.list_stations(include_inactive=True)
            if s["stage"] == "N1"
        }
        detail: dict[str, float] = {}
        for w in self.planning.list_wip(product_id):
            name = stage_by_station.get(w["station_id"])
            if name and w["qty"] > 0:
                detail[name] = detail.get(name, 0) + w["qty"]
        return sum(detail.values()), detail

    def stock_count_for_product(self, product_id: int) -> int:
        """在库卡数（三卡规则口径：在用卡正在消耗、不计入储备）。"""
        rows = self.prediction.cards.list_cards(status="在库", product_id=product_id)
        return len(rows)

    def compute_for_product(self, product_id: int) -> ProductDemand:
        key = self._cache_versions()
        hit = self._demand_cache.get(product_id)
        if hit and hit[0] == key:
            return hit[1]
        demand = self._compute_for_product_uncached(product_id)
        self._demand_cache[product_id] = (key, demand)
        return demand

    def _compute_for_product_uncached(self, product_id: int) -> ProductDemand:
        p = self.products.get(product_id)
        demand = ProductDemand(
            product_id=product_id,
            product_name=p["name"] if p else "?",
            horizon_days=self.horizon_days,
            touches_per_wafer=float(p["touches_per_wafer"]) if p else 0.0,
            wph=float(p["wph"]) if p else 0.0,
        )
        if p and p["wph"] and p["touches_per_wafer"]:
            demand.daily_touches_by_wph = float(p["wph"]) * float(p["touches_per_wafer"]) * 24.0

        demand.arrivals_by_day = self.arrivals_by_day(product_id, demand.horizon_days)
        demand.total_wafers = sum(demand.arrivals_by_day.values())
        demand.total_touches = demand.total_wafers * demand.touches_per_wafer

        demand.n1_wip_total, demand.n1_wip_detail = self.n1_wip_summary(product_id)

        # 三卡规则：只数【在库】卡（在用卡正在机台上消耗，不算储备）
        demand.stock_cards = self.stock_count_for_product(product_id)
        demand.three_card_gap = max(0, self.min_cards - demand.stock_cards)

        # 产能口径：全部非报废卡（在库+在用）的剩余寿命合计，用于采购缺口推算
        card_rows = self.cards_for_product(product_id)
        usable_preds = [
            self.prediction.predict_card(r["id"]) for r in card_rows if r["status"] != "报废"
        ]
        remainings = [p.remaining_touches for p in usable_preds if p.remaining_touches is not None]
        demand.capacity_touches = sum(remainings)
        demand.avg_remaining = (demand.capacity_touches / len(remainings)) if remainings else 0.0

        need_by_capacity = 0
        if demand.total_touches > 0 and demand.avg_remaining > 0:
            need_by_capacity = math.ceil(demand.total_touches / demand.avg_remaining)
        demand.cards_needed = need_by_capacity + demand.three_card_gap
        return demand

    def compute_all(self) -> list[ProductDemand]:
        return [self.compute_for_product(p["id"]) for p in self.products.list_all()]

    # ---------- 供采购/仓库复用 ----------

    def cards_for_product(self, product_id: int) -> list:
        return self.prediction.cards.list_cards(product_id=product_id)

    def product_alert_level(self, demand: ProductDemand) -> str:
        if demand.three_card_gap > 0:
            return AlertLevel.RED
        if demand.usable_cards == 0:
            return AlertLevel.RED
        return AlertLevel.OK
