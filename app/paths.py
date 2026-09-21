"""路径解析。

打包成 exe 后（PyInstaller 单文件），exe 自身所在目录就是"应用目录"，
config.ini 与默认数据目录都放在应用目录下；开发模式下则是项目根目录。
"""

import os
import sys


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_dir() -> str:
    """exe 或项目根目录所在文件夹。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_file() -> str:
    return os.path.join(app_dir(), "config.ini")


def default_data_dir() -> str:
    return os.path.join(app_dir(), "data")


def resource_path(rel_path: str) -> str:
    """打包资源的绝对路径：exe 单文件模式从解压目录（sys._MEIPASS）取。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return os.path.join(meipass, rel_path)
    return os.path.join(app_dir(), rel_path)
