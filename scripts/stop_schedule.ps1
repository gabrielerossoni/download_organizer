$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Content -LiteralPath (Join-Path $projectRoot '.stop-request') -Value 'stop' -Encoding ASCII
$task = Get-ScheduledTask -TaskName 'DownloadOrganizer' -ErrorAction SilentlyContinue
if ($task -and $task.Actions.WorkingDirectory -eq $projectRoot) { $task | Disable-ScheduledTask | Out-Null }
Write-Output 'Scansioni automatiche disabilitate; la scansione in corso si ferma tra i file.'
