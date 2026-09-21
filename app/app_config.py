"""config.ini 读写——只放"基础设施"配置（数据库文件位置）。

业务参数（报废线、预警阈值等）不放这里，它们存在数据库 settings 表里，
供工程师在软件"系统设置"页随时修改。
"""

import configparser
import os

from app import paths

SECTION = "database"
KEY_DB_PATH = "db_path"


def _read_raw() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(paths.config_file(), encoding="utf-8")
    return parser


def get_db_path() -> str:
    """数据库文件路径。优先取 config.ini，没有则用默认 <应用目录>/data/probe_card.db 并写回 ini。"""
    parser = _read_raw()
    db_path = parser.get(SECTION, KEY_DB_PATH, fallback="")
    if db_path:
        if not os.path.isabs(db_path):
            db_path = os.path.join(paths.app_dir(), db_path)
        return db_path
    db_path = os.path.join(paths.default_data_dir(), "probe_card.db")
    save_db_path(db_path)
    return db_path


def save_db_path(db_path: str) -> None:
    parser = _read_raw()
    if not parser.has_section(SECTION):
        parser.add_section(SECTION)
    parser.set(SECTION, KEY_DB_PATH, db_path)
    with open(paths.config_file(), "w", encoding="utf-8") as f:
        parser.write(f)
