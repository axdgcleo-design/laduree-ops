@echo off
echo.
echo  ==============================
echo    Laduree OPS System v1.1
echo    Port: localhost:5006
echo  ==============================
echo.
cd /d "%~dp0"
start "" "http://localhost:5006"
py app/server.py
pause