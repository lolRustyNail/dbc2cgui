@echo off
setlocal EnableDelayedExpansion

echo ============================================
echo   DBC2C - 自动打包脚本
echo ============================================
echo.

set APP_NAME=DBC2C
set VERSION=1.0.0
set ISCC_PATH="C:\Program Files (x86)\Inno Setup 7\ISCC.exe"

echo [1/4] 安装依赖...
if not exist "venv\Scripts\activate.bat" (
    echo 错误：找不到虚拟环境，请先运行: python -m venv venv
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
pip install pyinstaller --quiet 2>nul
if errorlevel 1 (
    echo 错误：依赖安装失败
    pause
    exit /b 1
)

echo [2/4] PyInstaller 打包...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
pyinstaller --name %APP_NAME% --windowed --noconfirm --clean ^
    --hidden-import cantools ^
    --hidden-import app.main_window ^
    --hidden-import app.convert_worker ^
    --hidden-import app.converter ^
    --hidden-import app.dbc_loader ^
    --hidden-import app.json_exporter ^
    --hidden-import app.models ^
    --hidden-import app.state ^
    --hidden-import app.widgets.condition_dialog ^
    --hidden-import app.widgets.condition_link_item ^
    --hidden-import app.widgets.custom_node_dialog ^
    --hidden-import app.widgets.dbc_tree ^
    --hidden-import app.widgets.link_item ^
    --hidden-import app.widgets.node_canvas ^
    --hidden-import app.widgets.signal_node_item ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    main.py
if errorlevel 1 (
    echo 错误：PyInstaller 打包失败
    pause
    exit /b 1
)
echo     打包完成: dist\%APP_NAME%\

echo [3/4] 制作安装程序...
if exist %ISCC_PATH% (
    %ISCC_PATH% installer.iss
    if errorlevel 1 (
        echo 错误：安装程序制作失败
        pause
        exit /b 1
    )
    echo     安装程序: installer_output\%APP_NAME%_Setup_%VERSION%.exe
) else (
    echo     警告：未找到 Inno Setup 7，跳过安装程序制作
    echo     默认路径：C:\Program Files (x86)\Inno Setup 7\ISCC.exe
    echo     下载地址：https://jrsoftware.org/isinfo.php
)

echo [4/4] 完成！
echo     可执行文件: dist\%APP_NAME%\%APP_NAME%.exe
echo     安装程序:   installer_output\%APP_NAME%_Setup_%VERSION%.exe
echo.
pause
