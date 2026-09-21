@echo off
REM ============================================================
REM  CP针卡采购管理系统 - 打包脚本
REM  产物: dist\probe_card_manager.exe （单文件，免安装，带图标）
REM  用法: 双击运行本脚本，或在命令行执行 build_exe.bat
REM ============================================================
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name probe_card_manager ^
  --icon assets\app.ico ^
  --add-data "assets;assets" ^
  --exclude-module pytest ^
  --exclude-module pytest_timeout ^
  --exclude-module _pytest ^
  main.py
echo.
echo 打包完成: dist\probe_card_manager.exe
pause
