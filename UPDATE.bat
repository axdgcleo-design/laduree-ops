@echo off
chcp 65001 > nul 2>&1
echo.
echo  ==============================
echo    LianYi OPS - Update
echo  ==============================
echo.

set SYSTEM=%~dp0
set UPDATE=%~dp0..\lianyi-ops-update

if not exist "%UPDATE%" (
    echo  [ERROR] 找不到更新資料夾：
    echo  %UPDATE%
    echo.
    echo  請確認 lianyi-ops-update 資料夾已放在 90_工具系統 底下
    pause
    exit /b 1
)

echo  更新來源：%UPDATE%
echo  系統路徑：%SYSTEM%
echo.
echo  即將覆蓋以下檔案：
echo    app\server.py
echo    app\templates\*.html
echo    app\static\css\style.css
echo.
set /p CONFIRM=確定更新？(y/n) 
if /i "%CONFIRM%" neq "y" (
    echo  已取消
    pause
    exit /b 0
)

echo.
echo  更新中...

if exist "%UPDATE%\app\server.py" (
    copy /y "%UPDATE%\app\server.py" "%SYSTEM%app\server.py" > nul
    echo  [OK] server.py
)

if exist "%UPDATE%\app\templates" (
    xcopy /y /q "%UPDATE%\app\templates\*" "%SYSTEM%app\templates\" > nul
    echo  [OK] templates\
)

if exist "%UPDATE%\app\static\css\style.css" (
    copy /y "%UPDATE%\app\static\css\style.css" "%SYSTEM%app\static\css\style.css" > nul
    echo  [OK] static\css\style.css
)

echo.
echo  ==============================
echo    更新完成！
echo  ==============================
echo.
echo  請重新啟動系統（雙擊 START.bat）
echo.
pause
