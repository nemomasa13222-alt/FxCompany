# fx_mt4/setup_scheduler.ps1
# Windows タスクスケジューラに30分ごとの実行を登録する
# 管理者権限で実行: 右クリック → PowerShellで実行

$TaskName   = "FxDemo_RangeBreak_30min"
$PythonPath = (Get-Command python).Source
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$Script     = "-m fx_mt4.run"

Write-Host "=== FxDemo タスクスケジューラ登録 ===" -ForegroundColor Cyan
Write-Host "Python : $PythonPath"
Write-Host "作業Dir: $ProjectDir"
Write-Host "スクリプト: $Script"

# 既存タスクを削除
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# アクション: python -m fx_mt4.run
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $Script `
    -WorkingDirectory $ProjectDir

# トリガー: 毎日 00:00 から30分おき（24時間）
$Triggers = @()
for ($h = 0; $h -lt 24; $h++) {
    for ($m = 0; $m -lt 60; $m += 30) {
        $time = "{0:D2}:{1:D2}" -f $h, $m
        $Triggers += New-ScheduledTaskTrigger -Daily -At $time
    }
}

# 設定
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Triggers `
    -Settings $Settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "`nタスク登録完了: $TaskName" -ForegroundColor Green
Write-Host "確認: タスクスケジューラ → $TaskName"

# テスト実行
$ans = Read-Host "今すぐテスト実行しますか？ (y/n)"
if ($ans -eq "y") {
    Set-Location $ProjectDir
    & $PythonPath -m fx_mt4.run
}
