"""程序入口：初始化数据库 → 自动备份 → 登录 → 主窗口。"""

from __future__ import annotations

import ctypes
import os
import sys
import traceback

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, APP_VERSION
from app import paths
from app.app_config import get_db_path
from app.database.connection import backup_database
from app.services.app_context import AppContext
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.styles import MAIN_QSS

APP_USER_MODEL_ID = "CP.PCMS.ProbeCardManager.1"


def _set_windows_app_identity() -> None:
    """给进程设置独立的 AppUserModelID。

    不设置的话，Windows 任务栏按宿主进程归组图标：开发态宿主是 python.exe，
    任务栏就会显示 Python 图标。设置后任务栏改用我们设置的窗口图标（assets/app.ico）。
    必须在创建任何窗口之前调用。
    """
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:  # noqa: BLE001
            pass  # 设置失败只影响任务栏图标归组，不阻断启动


def _install_excepthook():
    """未捕获异常弹窗提示，避免静默崩溃。"""

    def hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        sys.stderr.write(text)
        try:
            QMessageBox.critical(None, "程序异常", f"发生未处理的错误：\n\n{exc_value}")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def main() -> int:
    _install_excepthook()
    _set_windows_app_identity()
    app = QApplication(sys.argv)
    app.setApplicationName(f"{APP_NAME} v{APP_VERSION}")
    icon_path = paths.resource_path(os.path.join("assets", "app.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    app.setStyleSheet(MAIN_QSS)

    ctx = AppContext(get_db_path())
    keep = ctx.settings_repo.get_int("backup_keep_days", 30)
    backup_database(ctx.db, keep_days=keep)

    login = LoginDialog(ctx)
    if login.exec() != LoginDialog.DialogCode.Accepted:
        return 0

    win = MainWindow(ctx)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
