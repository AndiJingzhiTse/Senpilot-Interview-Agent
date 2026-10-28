[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Config,
    [ValidatePattern('^[A-Za-z0-9 _-]{1,80}$')]
    [string]$TaskName = 'SenpilotAgent',
    [switch]$Start
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not $Config) { $Config = Join-Path $repoRoot 'deploy/agent.json' }
$configPath = (Resolve-Path -LiteralPath $Config).Path
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
$pythonWindowless = Join-Path $repoRoot '.venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless -PathType Leaf)) {
    throw 'Create the project virtual environment before registering the task.'
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw 'A task with that name already exists. Review it before changing or replacing it.'
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonWindowless -Argument "-m senpilot.service --config `"$configPath`"" -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Senpilot Gmail worker with a persistent queue and local rotating logs.'
if ($PSCmdlet.ShouldProcess($TaskName, 'Register Senpilot at user logon')) {
    Push-Location -LiteralPath $repoRoot
    try {
        & $pythonPath -m senpilot.service --config $configPath --check
        if ($LASTEXITCODE -ne 0) { throw 'Local preflight failed. The task was not registered.' }
    } finally {
        Pop-Location
    }
    Register-ScheduledTask -TaskName $TaskName -InputObject $task | Out-Null
    if ($Start) { Start-ScheduledTask -TaskName $TaskName }
}
