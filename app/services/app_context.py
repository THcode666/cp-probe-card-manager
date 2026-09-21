"""应用上下文：组合根。

所有 repository / service 在这里创建并互相组装，界面层只从这一个入口拿依赖，
后续替换实现（如迁移到服务端架构）时只需改这个文件。
"""

from __future__ import annotations

from app.database.connection import Database
from app.repositories.audit_repo import AuditRepo
from app.repositories.cards_repo import CardsRepo
from app.repositories.planning_repo import PlanningRepo
from app.repositories.products_repo import ProductsRepo
from app.repositories.purchases_repo import PurchasesRepo
from app.repositories.settings_repo import SettingsRepo
from app.repositories.users_repo import UsersRepo
from app.services.auth_service import AuthService
from app.services.card_service import CardService
from app.services.demand_service import DemandService
from app.services.prediction_service import PredictionService
from app.services.purchase_service import PurchaseService
from app.services.warehouse_service import WarehouseService


class AppContext:
    def __init__(self, db_path: str):
        self.db = Database(db_path)

        # 数据访问层
        self.settings_repo = SettingsRepo(self.db)
        self.users_repo = UsersRepo(self.db)
        self.products_repo = ProductsRepo(self.db)
        self.cards_repo = CardsRepo(self.db)
        self.planning_repo = PlanningRepo(self.db)
        self.purchases_repo = PurchasesRepo(self.db)
        self.audit_repo = AuditRepo(self.db)

        # 初始化（默认配置 + 内置管理员账号）
        self.settings_repo.ensure_defaults()
        self.users_repo.ensure_builtin_accounts()

        # 业务层
        self.auth = AuthService(self.users_repo, self.audit_repo, self.settings_repo)
        self.prediction = PredictionService(
            self.cards_repo, self.products_repo, self.settings_repo
        )
        self.demand = DemandService(
            self.products_repo, self.planning_repo, self.prediction, self.settings_repo
        )
        self.purchase = PurchaseService(
            self.products_repo, self.purchases_repo, self.demand, self.prediction, self.settings_repo
        )
        self.cards = CardService(
            self.cards_repo, self.products_repo, self.audit_repo, self.settings_repo, self.users_repo
        )
        self.warehouse = WarehouseService(self.cards_repo, self.audit_repo)

        # 当前登录用户（登录成功后由界面写入）：{id, username, role}
        self.current_user: dict | None = None
        # 登录时若仍在使用内置默认密码则置 True，主窗口弹出安全提醒
        self.using_default_password: bool = False

    @property
    def operator(self) -> str:
        return self.current_user["username"] if self.current_user else "system"

    @property
    def is_admin(self) -> bool:
        return bool(self.current_user and self.current_user["role"] == "管理员")
