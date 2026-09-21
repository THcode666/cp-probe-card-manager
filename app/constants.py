"""全局常量与枚举。所有会被界面引用的"词汇"统一定义在这里，避免魔法字符串散落各处。"""

from enum import StrEnum


class CardStatus(StrEnum):
    """针卡状态（简化三状态）。"""

    IN_STOCK = "在库"      # 仓库里可用
    IN_USE = "在用"        # 装在机台上测试中
    SCRAPPED = "报废"      # 已到寿命下线

    @classmethod
    def values(cls) -> list[str]:
        return [s.value for s in cls]


class Role(StrEnum):
    """用户角色。"""

    ADMIN = "管理员"
    ENGINEER = "工程师"


class PurchaseStatus(StrEnum):
    """采购单状态。"""

    ORDERED = "已下单"
    RECEIVED = "已到货"
    CANCELLED = "已取消"

    @classmethod
    def values(cls) -> list[str]:
        return [s.value for s in cls]


class AlertLevel(StrEnum):
    """预警级别。"""

    OK = "正常"
    YELLOW = "黄色预警"
    RED = "红色预警"
    UNKNOWN = "数据不足"


# 默认全局配置项（首次建库时写入 settings 表，之后一切以数据库里的值为准，
# 工程师可在"系统设置"页随时修改——代码里只提供出厂默认值）。
DEFAULT_SETTINGS: dict[str, str] = {
    "scrap_needle_len_um": "22",          # 针长报废线（um）
    "rated_touches_default": "4800000",   # 默认针卡最大测试量（次）
    "warn_yellow_pct": "90",              # 寿命达成率低于该百分比 → 黄色预警
    "warn_red_pct": "80",                 # 寿命达成率低于该百分比 → 红色预警
    "scrap_remind_days": "14",            # 预计报废日期提前 N 天提醒
    "purchase_buffer_days": "7",          # 采购缓冲天数（提前期 + 缓冲 = 最晚下单日）
    "min_cards_per_product": "3",         # 每个产品最少在库针卡数（三卡规则）
    "demand_horizon_days": "14",          # 到达量/需求预测展望天数
    "min_points_for_own_fit": "3",        # 单卡自有拟合所需最少数据点数
    "backup_keep_days": "30",             # 数据库备份保留天数
    "default_wph": "0",                   # 新产品的默认 WPH（0=未配置）
}

# 自助注册激活码（仓库公开版为占位值，部署前请在 constants.py 中改成自己的固定值）
ACTIVATION_CODE = "change-me-activation"

# 【用户管理】模块的进入密码（公开版为占位值，部署前请自行修改）
USER_MODULE_PASSWORD = "change-me-admin"
