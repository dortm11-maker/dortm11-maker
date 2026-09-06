@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 뉴스NOW - 깃허브 원클릭 자동 업로드 (Render 자동 배포)

echo ================================================================
echo   [뉴스NOW] 깃허브 원클릭 자동 업로드 ^& Render 클라우드 배포
echo ================================================================
echo.

:: Git 경로 탐색
set "GIT_CMD=git"
where git >nul 2>nul
if %errorlevel% neq 0 (
    if exist "C:\Program Files\Git\cmd\git.exe" (
        set "GIT_CMD=C:\Program Files\Git\cmd\git.exe"
    )
)

echo [1/3] 변경된 파일들을 수집하고 있습니다...
"%GIT_CMD%" add -A

echo [2/3] 최신 변경사항을 저장하고 있습니다...
"%GIT_CMD%" commit -m "뉴스NOW 사이트 최신 업데이트"

echo [3/3] 깃허브 원격 저장소로 전송하고 있습니다...
"%GIT_CMD%" push origin main

echo.
echo ================================================================
echo   ★ 모든 변경사항 전송 작업이 완료되었습니다!
echo   ★ Render 클라우드에서 1~2분 뒤 자동으로 최신 버전이 반영됩니다.
echo ================================================================
echo.
pause
