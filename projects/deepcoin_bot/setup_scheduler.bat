@echo off
echo ============================================
echo DeepCoin Bot - Task Scheduler 등록
echo ============================================

set BOT_DIR=C:\Users\g8428\.local\bin\experiment\deepcoin_bot
set PYTHON=python

echo.
echo [1] 매일 자정 복기/튜닝 (daily_review.py) 등록...
schtasks /create /tn "DeepCoin_DailyReview" ^
  /tr "%PYTHON% %BOT_DIR%\daily_review.py >> %BOT_DIR%\trade_logs\review.log 2>&1" ^
  /sc daily ^
  /st 00:05 ^
  /f ^
  /rl HIGHEST
if %errorlevel%==0 (echo    OK: 매일 00:05 실행 예약됨) else (echo    [!] 등록 실패)

echo.
echo [2] 봇 상태 확인 작업 (매시간) 등록...
schtasks /create /tn "DeepCoin_HealthCheck" ^
  /tr "curl -s http://localhost:5000/api/status > nul 2>&1" ^
  /sc hourly ^
  /f
if %errorlevel%==0 (echo    OK: 매시간 상태 확인) else (echo    [!] 등록 실패)

echo.
echo [3] 등록된 작업 확인:
schtasks /query /tn "DeepCoin_DailyReview" /fo list 2>nul
schtasks /query /tn "DeepCoin_HealthCheck" /fo list 2>nul

echo.
echo ============================================
echo 완료! 매일 00:05에 Claude가 자동으로
echo 매매 복기 + 파라미터 튜닝을 실행합니다.
echo ============================================
pause
