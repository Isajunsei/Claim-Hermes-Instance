# health_check.ps1
# スクリプトが正常に動いているか確認する。
# 緑 = 正常稼働中 / 赤 = 止まっている（要対処）

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$StatusFile = Join-Path $ScriptDir "status.json"
$LogFile    = Join-Path $ScriptDir "log.txt"

Clear-Host
Write-Host ""
Write-Host "════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "   Hermes OCI Claim-Slot  —  Health Check" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── status.json が存在しない場合 ──
if (-not (Test-Path $StatusFile)) {
    Write-Host "  [RED] スクリプトがまだ一度も起動されていません。" -ForegroundColor Red
    Write-Host ""
    Write-Host "  → claim_slot.bat をダブルクリックして起動してください。" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Enterで閉じる"
    exit 1
}

# ── status.json を読む ──
try {
    $status = Get-Content $StatusFile -Raw | ConvertFrom-Json
} catch {
    Write-Host "  [RED] status.json の読み込みに失敗しました: $_" -ForegroundColor Red
    Read-Host "Enterで閉じる"
    exit 1
}

$state       = $status.state
$lastUpdate  = $status.last_update
$totalAttempts = $status.total_attempts
$sessionAttempts = $status.session_attempts

# ── 最終更新から何分経ったか ──
$staleMinutes = 999
if ($lastUpdate) {
    try {
        $lastDt       = [datetime]::ParseExact($lastUpdate, "yyyy-MM-dd HH:mm:ss", $null)
        $staleMinutes = [int]((Get-Date) - $lastDt).TotalMinutes
    } catch {}
}

# ── 判定ロジック ──
$isSuccess = ($state -eq "success")
$isStopped = ($state -eq "stopped") -or ($staleMinutes -gt 5 -and -not $isSuccess)

if ($isSuccess) {
    # ════ SUCCESS ════
    Write-Host "  ✅  SUCCESS — インスタンス取得済み！" -ForegroundColor Green
    Write-Host ""
    if ($status.public_ip) {
        Write-Host "  パブリックIP : $($status.public_ip)" -ForegroundColor Green
        $keyPath = Join-Path $ScriptDir "ssh-key-2026-06-21.key"
        Write-Host "  SSH接続     : ssh -i `"$keyPath`" ubuntu@$($status.public_ip)" -ForegroundColor Green
    }
    Write-Host ""
    Write-Host "  SUCCESS.txt に詳細と次のステップが書かれています。" -ForegroundColor Cyan

} elseif ($isStopped) {
    # ════ 停止中（要対処）════
    Write-Host "  ❌  停止中 — スクリプトが動いていません！" -ForegroundColor Red
    Write-Host ""
    Write-Host "  最終更新 : $lastUpdate" -ForegroundColor Red
    Write-Host "  経過時間 : ${staleMinutes}分前" -ForegroundColor Red
    Write-Host "  状態     : $state" -ForegroundColor Red
    Write-Host ""
    Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkRed
    Write-Host "  ▶ 対処方法" -ForegroundColor Yellow
    Write-Host "    1. claim_slot.bat をダブルクリックして起動" -ForegroundColor Yellow
    Write-Host "    2. 黒いウィンドウが開き [TOTAL #N] が流れていればOK" -ForegroundColor Yellow
    Write-Host "    3. PCのスリープ設定を「なし」に変更してください" -ForegroundColor Yellow
    Write-Host "       (設定 → 電源とスリープ → スリープ → なし)" -ForegroundColor Yellow
    Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkRed

} else {
    # ════ 正常稼働中 ════
    Write-Host "  ✅  正常稼働中 — 在庫待ちでリトライ継続中" -ForegroundColor Green
    Write-Host ""
    Write-Host "  状態           : $state" -ForegroundColor Green
    Write-Host "  最終更新       : $lastUpdate  (${staleMinutes}分前)" -ForegroundColor Green
    Write-Host "  今セッション   : ${sessionAttempts} 回試行" -ForegroundColor Green
    Write-Host "  累計           : ${totalAttempts} 回試行" -ForegroundColor Green
}

# ── 最新ログ（最後の10行）──
Write-Host ""
Write-Host "  ── 最新ログ ────────────────────────────────" -ForegroundColor DarkCyan
if (Test-Path $LogFile) {
    $lines = Get-Content $LogFile -Tail 10
    foreach ($line in $lines) {
        if ($line -match "SUCCESS") {
            Write-Host "  $line" -ForegroundColor Green
        } elseif ($line -match "error|Error|ERROR") {
            Write-Host "  $line" -ForegroundColor Red
        } else {
            Write-Host "  $line" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "  (ログファイルがまだありません)" -ForegroundColor DarkGray
}

Write-Host ""
Read-Host "Enterで閉じる"
