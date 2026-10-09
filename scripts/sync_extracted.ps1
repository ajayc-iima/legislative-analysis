# Mirrors the live C: extraction log back to the D: data path.
# D: cannot be written by the worker (hung flushes wedge it), so this
# validated copy runs separately: only complete JSON lines are copied,
# via a temp file + atomic rename — readers never see a torn file.
# Monotonic guard: never replaces the destination with fewer records.
# Usage (from repo root):
#   powershell -File scripts/sync_extracted.ps1            # once
#   powershell -File scripts/sync_extracted.ps1 -Loop 600  # every 10 min
param([int]$Loop = 0)
$REPO = Split-Path $PSScriptRoot -Parent
$SRC = "C:\Users\chou_\AppData\Local\Temp\opencode\extract_run\extracted.jsonl"
$DST = Join-Path $REPO "data\extracted\extracted.jsonl"

function Sync-Once {
    if (-not (Test-Path $SRC)) { Write-Output "source missing, abort"; return }
    $raw = $null
    for ($i = 1; $i -le 3; $i++) {
        try { $raw = Get-Content $SRC -ErrorAction Stop; break }
        catch { Start-Sleep -Seconds 5 }
    }
    if (-not $raw) { Write-Output "source unreadable, abort"; return }
    $valid = @()
    foreach ($line in $raw) {
        if (-not $line.Trim()) { continue }
        try { $line | ConvertFrom-Json | Out-Null; $valid += $line }
        catch { continue }
    }
    $old = 0
    if (Test-Path $DST) {
        $old = @(Get-Content $DST -ErrorAction SilentlyContinue).Count
    }
    if ($valid.Count -lt $old) {
        Write-Output "abort: source $($valid.Count) < dest $old (no backward sync)"
        return
    }
    $tmp = "$DST.tmp"
    Set-Content $tmp -Value $valid -Encoding utf8
    Move-Item $tmp $DST -Force
    Write-Output "$(Get-Date -Format 'HH:mm:ss') synced $($valid.Count) records -> $DST"
}

if ($Loop -le 0) { Sync-Once }
else { while ($true) { try { Sync-Once } catch { Write-Output "sync failed: $_" }; Start-Sleep -Seconds $Loop } }
