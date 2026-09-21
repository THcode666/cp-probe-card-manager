"""寿命预测服务（磨损曲线拟合与预警判定）。

模型思路
========
每张卡的磨损数据是若干个 (累计测试量 cum_touches, 针长 needle_len) 点。
同一产品的针卡初始针长相同、磨损规律相近，因此：

1. 单卡自有拟合：数据点 >= min_points_for_own_fit 时，对卡自身做线性回归
       needle_len = a + b * cum_touches   (b < 0，磨得越多针越短)
   外推 needle_len 降到报废线时的累计测试量：
       touches_at_scrap = (a - scrap_len) / (-b)
2. 类型拟合（"同类型大模型"）：数据点不足时，借用该产品下所有针卡
   （含已报废的完整寿命数据）汇总回归得到的平均磨损曲线做同样的外推。
3. 寿命达成率 = touches_at_scrap / 生效额定寿命，低于配置阈值分级预警。
4. 消耗速度：优先取最近两次更新的 (测试量差 / 天数差)；不足时退化为
   首末两点平均速度，用于估算预计报废日期。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

import numpy as np

from app.constants import AlertLevel
from app.repositories.cards_repo import CardsRepo
from app.repositories.products_repo import ProductsRepo
from app.repositories.settings_repo import SettingsRepo
from app.utils import timeutil


@dataclass
class CardPrediction:
    card_id: int
    card_name: str = ""
    status: str = ""
    product_names: str = ""
    points_count: int = 0
    last_touches: float | None = None
    last_len: float | None = None
    last_update_date: str | None = None
    rated_touches: float = 0.0
    touches_at_scrap: float | None = None   # 预测到报废线时的累计测试量
    remaining_touches: float | None = None  # 剩余可测次数
    achievement_pct: float | None = None    # 寿命达成率 %
    alert_level: str = AlertLevel.UNKNOWN
    daily_touch_rate: float | None = None   # 消耗速度（次/天）
    scrap_date: str | None = None           # 预计报废日期
    days_to_scrap: float | None = None
    curve_source: str = "none"              # own=自身拟合 / product=类型曲线 / none
    curve_slope: float | None = field(default=None, repr=False)   # um/次
    curve_intercept: float | None = field(default=None, repr=False)
    product_curve: tuple | None = field(default=None, repr=False)  # 供图表叠加


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """普通最小二乘 y = b*x + a；点数不足或 x 无变化时返回 None。"""
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if float(np.ptp(x)) <= 0:
        return None
    coef, *_ = np.linalg.lstsq(np.vstack([x, np.ones_like(x)]).T, y, rcond=None)
    return float(coef[0]), float(coef[1])


class PredictionService:
    def __init__(self, cards_repo: CardsRepo, products_repo: ProductsRepo, settings_repo: SettingsRepo):
        self.cards = cards_repo
        self.products = products_repo
        self.settings = settings_repo

    # ---------- 配置项 ----------

    @property
    def scrap_len(self) -> float:
        return self.settings.get_float("scrap_needle_len_um", 22.0)

    @property
    def default_rated(self) -> float:
        return self.settings.get_float("rated_touches_default", 4_800_000)

    @property
    def yellow_pct(self) -> float:
        return self.settings.get_float("warn_yellow_pct", 90.0)

    @property
    def red_pct(self) -> float:
        return self.settings.get_float("warn_red_pct", 80.0)

    @property
    def scrap_remind_days(self) -> int:
        return self.settings.get_int("scrap_remind_days", 14)

    @property
    def min_own_points(self) -> int:
        return self.settings.get_int("min_points_for_own_fit", 3)

    # ---------- 拟合 ----------

    def product_curve_for(self, product_id: int) -> tuple[float, float] | None:
        """同产品全部针卡汇总拟合的平均磨损曲线 (b, a)。"""
        pts = self.cards.update_points_for_product(product_id)
        return _linear_fit([p["cum_touches"] for p in pts], [p["needle_len"] for p in pts])

    def _touches_at_scrap(self, slope: float, intercept: float) -> float | None:
        if slope >= 0:  # 针长不随测试量下降，数据异常，不外推
            return None
        t = (intercept - self.scrap_len) / (-slope)
        return t if t > 0 else None

    def _effective_rated(self, card_row, product_ids: list[int]) -> float:
        if card_row["rated_touches"]:
            return float(card_row["rated_touches"])
        rated = 0.0
        for pid in product_ids:
            p = self.products.get(pid)
            if p and p["rated_touches"]:
                rated = max(rated, float(p["rated_touches"]))
        return rated if rated > 0 else self.default_rated

    @staticmethod
    def _daily_rate(updates: list) -> float | None:
        """最近两次（按日期）更新的消耗速度；不足则取首末平均。"""
        if not updates:
            return None
        ordered = sorted(updates, key=lambda r: (r["update_date"], r["id"] if "id" in r.keys() else 0))
        if len(ordered) >= 2:
            t1, t2 = float(ordered[-2]["cum_touches"]), float(ordered[-1]["cum_touches"])
            d1, d2 = timeutil.parse_date(ordered[-2]["update_date"]), timeutil.parse_date(ordered[-1]["update_date"])
            days = (d2 - d1).days
            if days > 0 and t2 > t1:
                return (t2 - t1) / days
        t1, t2 = float(ordered[0]["cum_touches"]), float(ordered[-1]["cum_touches"])
        d1, d2 = timeutil.parse_date(ordered[0]["update_date"]), timeutil.parse_date(ordered[-1]["update_date"])
        days = (d2 - d1).days
        if days > 0 and t2 > t1:
            return (t2 - t1) / days
        return None

    # ---------- 预测 ----------

    def predict_card(self, card_id: int) -> CardPrediction:
        pred = CardPrediction(card_id=card_id)
        card = self.cards.get(card_id)
        if not card:
            return pred
        pred.card_name = card["name"]
        pred.status = card["status"]

        product_ids = self.cards.product_ids_of_card(card_id)
        names = []
        for pid in product_ids:
            p = self.products.get(pid)
            if p:
                names.append(p["name"])
        pred.product_names = ", ".join(names)
        pred.rated_touches = self._effective_rated(card, product_ids)

        updates = self.cards.updates_for_card(card_id)
        pred.points_count = len(updates)
        if not updates:
            return pred
        last = max(updates, key=lambda r: r["cum_touches"])
        pred.last_touches = float(last["cum_touches"])
        pred.last_len = float(last["needle_len"])
        pred.last_update_date = last["update_date"]

        pts = self.cards.update_points_for_card(card_id)
        xs = [float(p["cum_touches"]) for p in pts]
        ys = [float(p["needle_len"]) for p in pts]

        touches_at_scrap: float | None = None
        if len(pts) >= self.min_own_points:
            fit = _linear_fit(xs, ys)
            if fit:
                touches_at_scrap = self._touches_at_scrap(*fit)
                if touches_at_scrap is not None:
                    pred.curve_source = "own"
                    pred.curve_slope, pred.curve_intercept = fit

        if touches_at_scrap is None:
            best: tuple[float, float] | None = None
            best_n = -1
            for pid in product_ids:
                pool = self.cards.update_points_for_product(pid)
                fit = _linear_fit([float(p["cum_touches"]) for p in pool], [float(p["needle_len"]) for p in pool])
                if fit and len(pool) > best_n:
                    best, best_n = fit, len(pool)
                    pred.product_curve = fit
            if best:
                touches_at_scrap = self._touches_at_scrap(*best)
                if touches_at_scrap is not None:
                    pred.curve_source = "product"
                    pred.curve_slope, pred.curve_intercept = best

        pred.touches_at_scrap = touches_at_scrap
        if touches_at_scrap is not None:
            pred.remaining_touches = max(0.0, touches_at_scrap - pred.last_touches)
            if pred.rated_touches > 0:
                pred.achievement_pct = touches_at_scrap / pred.rated_touches * 100.0
            pred.alert_level = self._level_for(pred)

        pred.daily_touch_rate = self._daily_rate(updates)
        if pred.daily_touch_rate and pred.remaining_touches is not None and pred.remaining_touches > 0:
            pred.days_to_scrap = pred.remaining_touches / pred.daily_touch_rate
            pred.scrap_date = (
                _dt.date.today() + _dt.timedelta(days=round(pred.days_to_scrap))
            ).isoformat()
        elif pred.last_len is not None and pred.last_len <= self.scrap_len:
            pred.scrap_date = "已到报废线"
        return pred

    def _level_for(self, pred: CardPrediction) -> str:
        if pred.last_len is not None and pred.last_len <= self.scrap_len:
            return AlertLevel.RED
        if pred.achievement_pct is None:
            return AlertLevel.UNKNOWN
        if pred.achievement_pct < self.red_pct:
            return AlertLevel.RED
        if pred.achievement_pct < self.yellow_pct:
            return AlertLevel.YELLOW
        return AlertLevel.OK

    def predict_all(self) -> list[CardPrediction]:
        return [self.predict_card(row["id"]) for row in self.cards.list_cards()]

    def scrap_remind_cards(self) -> list[CardPrediction]:
        """预计报废日期落在提醒窗口内、且仍在用的卡。"""
        today = _dt.date.today()
        horizon = today + _dt.timedelta(days=self.scrap_remind_days)
        result = []
        for pred in self.predict_all():
            if pred.status == "报废" or not pred.scrap_date:
                continue
            if pred.last_len is not None and pred.last_len <= self.scrap_len:
                result.append(pred)
                continue
            try:
                if today <= timeutil.parse_date(pred.scrap_date) <= horizon:
                    result.append(pred)
            except ValueError:
                continue
        return result
