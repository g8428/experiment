$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c C:\Users\g8428\.local\bin\experiment\deepcoin_bot\run_review.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At "00:05"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -RestartCount 1
Register-ScheduledTask -TaskName "DeepCoin_DailyReview" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force
Write-Host "등록 완료"
Get-ScheduledTask -TaskName "DeepCoin_DailyReview" | Select TaskName, State
