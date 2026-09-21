"""全部建表 SQL 与首次初始化。

设计要点：
- cards 与 products 是多对多，用 card_products 关联表；
- card_updates 是磨损曲线的数据源，每次更新一条记录（日期+累计测试量+针长）；
- wip 按产品×站点一条记录，直接覆盖更新；
- 所有时间统一存本地时间字符串，日期 'YYYY-MM-DD'，时间戳 'YYYY-MM-DD HH:MM:SS'。
"""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    updated_at  TEXT,
    updated_by  TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,
    touches_per_wafer REAL NOT NULL DEFAULT 0,      -- 测一片 wafer 消耗的测试量（次）
    wph               REAL NOT NULL DEFAULT 0,      -- 每小时测片数（WPH）
    initial_len_um    REAL NOT NULL DEFAULT 0,      -- 新卡初始针长（um）
    rated_touches     REAL NOT NULL DEFAULT 0,      -- 厂商额定寿命（次），0=用全局默认
    lead_time_days    REAL NOT NULL DEFAULT 0,      -- 采购提前期（天），0=未配置
    note              TEXT NOT NULL DEFAULT '',
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,             -- 针卡名（如 RR-01），全库唯一
    status        TEXT NOT NULL,                    -- 在库 / 在用 / 报废
    rated_touches REAL NOT NULL DEFAULT 0,          -- 单卡额定寿命覆盖值，0=按产品/全局
    in_stock_date TEXT NOT NULL,                    -- 入库日期
    scrapped_date TEXT,                             -- 报废日期
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS card_products (
    card_id    INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    PRIMARY KEY (card_id, product_id)
);

CREATE TABLE IF NOT EXISTS card_updates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id     INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    update_date TEXT NOT NULL,                       -- 数据日期
    cum_touches REAL NOT NULL,                       -- 累计测试量（次，自新卡起）
    needle_len  REAL NOT NULL,                       -- 针长（um）
    operator    TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_card_updates_card ON card_updates(card_id, cum_touches);

CREATE TABLE IF NOT EXISTS stations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,                -- 站点名（如 LOT、FT1）
    days_to_cp REAL NOT NULL DEFAULT 0,             -- 到 CP 周转时间（天，可小数）
    stage      TEXT NOT NULL DEFAULT 'N2',          -- N1=前段（只记数量）/ N2=临近 CP（记时间+数量）
    active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS wip (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    qty        INTEGER NOT NULL DEFAULT 0,          -- 该站点该产品当前片数
    updated_at TEXT,
    updated_by TEXT,
    UNIQUE (product_id, station_id)
);

CREATE TABLE IF NOT EXISTS purchases (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty        INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    eta_date   TEXT NOT NULL,
    status     TEXT NOT NULL,                       -- 已下单 / 已到货 / 已取消
    operator   TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    operator TEXT NOT NULL,
    module   TEXT NOT NULL,
    action   TEXT NOT NULL,
    detail   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
"""


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL)
    # 轻量迁移：老库补 password_recover 列（管理员可查看密码的可逆存储副本）
    cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
    if "password_recover" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN password_recover TEXT")
    # 轻量迁移：登录防暴力破解字段
    if "failed_attempts" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0")
    if "locked_until" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN locked_until TEXT")
    # 轻量迁移：老库补 stations.stage 列（历史站点默认归入 N2）
    cols = {row[1] for row in con.execute("PRAGMA table_info(stations)")}
    if "stage" not in cols:
        con.execute("ALTER TABLE stations ADD COLUMN stage TEXT NOT NULL DEFAULT 'N2'")
