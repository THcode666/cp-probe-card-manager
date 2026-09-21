"""针卡管理系统。

模块分层（职责对齐，自上而下单向依赖）：
    ui/          界面层：只做展示与交互，不含业务规则
    services/    业务层：预测、需求、采购、仓库流转等业务规则
    repositories/数据层：所有 SQL 都在这里，其他层不接触 SQL
    database/    连接管理：SQLite 连接、锁重试、备份
    utils/       工具：Excel 导出、输入校验
"""

APP_NAME = "CP针卡采购管理系统"
APP_VERSION = "1.1.0"
