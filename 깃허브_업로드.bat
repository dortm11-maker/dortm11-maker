@echo off
cd /d "%~dp0"
title 뉴스NOW - 깃허브 코드 자동 업로드 (Render 배포)

echo ================================================================
echo   [뉴스NOW] 깃허브 코드 자동 업로드 & Render 클라우드 배포
echo ================================================================
echo.

echo [1/3] 변경된 파일들을 정리하고 있습니다...
"C:\Program Files\Git\cmd\git.exe" add -A

echo [2/3] 최신 변경사항을 저장하고 있습니다...
"C:\Program Files\Git\cmd\git.exe" commit -m "뉴스NOW 사이트 최신 업데이트"

echo [3/3] 깃허브로 안전하게 전송하고 있습니다...
"C:\Program Files\Git\cmd\git.exe" push origin main

echo.
echo ================================================================
echo   깃허브 전송 작업이 완료되었습니다!
echo   Render 클라우드 서버에서 1~2분 내로 자동 반영됩니다.
echo ================================================================
echo.
pause
