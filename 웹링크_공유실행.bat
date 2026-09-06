@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 뉴스NOW - 외부 공유 웹링크 생성기

:: 1. Flask 서버 실행 확인 (5100번 포트)
netstat -ano | findstr :5100 > nul
if errorlevel 1 (
    echo [안내] 뉴스 서버를 백그라운드로 실행합니다...
    start "" python app.py
    timeout /t 2 > nul
)

:: 2. 터널 러너 실행 (주소 자동 추출 + 클립보드 복사 + 안내)
python tunnel_runner.py

pause
