@echo off
chcp 65001 > nul
title 뉴스NOW - 실시간 언론사 RSS 뉴스

echo ================================================================
echo   📰 뉴스NOW - 실시간 언론사 RSS 뉴스 뷰어
echo ================================================================
echo.
echo [1/3] 필요한 패키지를 확인합니다...

pip install -r requirements.txt --quiet 2>nul

echo [2/3] 로컬 서버를 시작합니다...
echo [3/3] 잠시 후 브라우저가 자동으로 열립니다.
echo.
echo  * 접속 주소: http://127.0.0.1:5100
echo  * 종료하려면 이 창을 닫으세요.
echo.
echo ================================================================

python app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [오류] 실행 중 문제가 발생했습니다.
    echo  - Python이 설치되어 있는지 확인하세요.
    echo  - pip install -r requirements.txt 명령을 먼저 실행해보세요.
    echo.
    pause
)
