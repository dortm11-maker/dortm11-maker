@echo off
cd /d "%~dp0"
title News NOW Server
echo ===================================================
echo   News NOW Server Starting...
echo   Open: http://127.0.0.1:5100
echo ===================================================

start http://127.0.0.1:5100

"C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe" app.py
if %ERRORLEVEL% NEQ 0 (
    python app.py
)
pause
