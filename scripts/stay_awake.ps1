# Keeps idle sleep (Modern Standby) off while the extraction runs.
# The extraction worker dies when the machine sleeps (network drops
# mid-API-call and the background job is reaped). This holds
# ES_CONTINUOUS|ES_SYSTEM_REQUIRED so idle standby cannot engage.
# Run detached: Start-Process powershell -ArgumentList "-NoProfile",
#   "-File", "D:\ISB\legislative-analysis\scripts\stay_awake.ps1" -WindowStyle Hidden
# Stop it when the run finishes: Stop-Process -Name powershell (check first).
# NOTE: closing the laptop lid still sleeps the machine — keep it open.

Add-Type -Name StayAwake -MemberDefinition @'
[DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
'@ -Namespace Win32

$ES_CONTINUOUS = 0x80000000
$ES_SYSTEM_REQUIRED = 0x1
while ($true) {
    [Win32.StayAwake]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED) | Out-Null
    Start-Sleep -Seconds 50
}
