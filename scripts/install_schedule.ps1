[CmdletBinding(SupportsShouldProcess)]
param([ValidateRange(1, 1440)][int]$IntervalMinutes = 5)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$scriptPath = Join-Path $projectRoot 'organizer.py'
if (!(Test-Path -LiteralPath $pythonPath) -or !(Test-Path -LiteralPath (Join-Path $projectRoot 'config\config.json'))) {
    throw 'Esegui prima Setup.bat.'
}
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $scriptPath + '"') -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$existing = Get-ScheduledTask -TaskName 'DownloadOrganizer' -ErrorAction SilentlyContinue
if ($existing -and $existing.Actions.WorkingDirectory -ne $projectRoot) {
    throw 'Il nome DownloadOrganizer appartiene a un altro progetto: non viene modificato.'
}
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
if ($PSCmdlet.ShouldProcess('DownloadOrganizer', "Registra scansione ogni $IntervalMinutes minuti")) {
    Register-ScheduledTask -TaskName 'DownloadOrganizer' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Output "Scansione ogni $IntervalMinutes minuti; nessun processo residente tra le scansioni."
}
