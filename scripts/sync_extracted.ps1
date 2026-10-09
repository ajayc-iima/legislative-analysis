# Mirrors the live C: extraction log back to the D: data path.
# D: cannot be written by the worker (hung flushes wedge it), so this
# validated copy runs separately: only complete JSON lines are copied,
# via a temp file + atomic rename — readers never see a torn file.
# Monotonic guard: never replaces the destination with fewer records.
# Usage (from repo root):
#   powershell -File scripts/sync_extracted.ps1                 # once
#   powershell -File scripts/sync_extracted.ps1 -Loop 60 -Every 50  # sync
#     whenever the source grows by >=50 records (polled each minute)
param([int]$Loop = 0, [int]$Every = 50)
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

function Get-Count($Path) {
    try { return @(Get-Content $Path -ErrorAction Stop).Count }
    catch { return -1 }
}

if ($Loop -le 0) { Sync-Once }
else {
    Sync-Once
    $last = Get-Count $DST
    while ($true) {
        Start-Sleep -Seconds $Loop
        try {
            $now = Get-Count $SRC
            if ($now -ge 0 -and ($now - $last) -ge $Every) {
                Sync-Once
                $last = Get-Count $DST
            }
        }
        catch { Write-Output "watch failed: $_" }
    }
}
