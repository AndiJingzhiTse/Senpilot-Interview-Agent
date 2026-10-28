[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Config,
    [string]$PythonPath,
    [ValidatePattern('^[A-Za-z0-9 _-]{1,80}$')]
    [string]$TaskName = 'SenpilotAgent',
    [switch]$Start,
    [switch]$Update
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not $Config) { $Config = Join-Path $repoRoot 'deploy/agent.json' }
$configPath = (Resolve-Path -LiteralPath $Config).Path
if (-not $PythonPath) {
    $PythonPath = Join-Path $repoRoot 'artifacts/runtime/venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        $PythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
    }
}
$runtimePython = (Resolve-Path -LiteralPath $PythonPath).Path
$pythonWindowless = Join-Path (Split-Path -Parent $runtimePython) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless -PathType Leaf)) {
    throw 'Create the project virtual environment before registering the task.'
}
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask -and -not $Update) {
    throw 'A task with that name already exists. Review it, then use -Update for a runtime change.'
}
if ($Update -and -not $existingTask) {
    throw 'The task does not exist. Omit -Update to register it.'
}
$arguments = "-m senpilot.service --config `"$configPath`""
if ($Update -and ($existingTask.Actions.Count -ne 1 -or $existingTask.Actions[0].WorkingDirectory -ne $repoRoot -or $existingTask.Actions[0].Arguments -ne $arguments)) {
    throw 'The existing task does not match this project and configuration. It was not changed.'
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonWindowless -Argument $arguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Senpilot Gmail worker with a persistent queue and local rotating logs.'
if ($PSCmdlet.ShouldProcess($TaskName, $(if ($Update) { 'Update Senpilot runtime' } else { 'Register Senpilot at user logon' }))) {
    if ($existingTask -and $existingTask.State -eq 'Running') {
        throw 'Stop the existing task before updating its runtime.'
    }
    Push-Location -LiteralPath $repoRoot
    try {
        for ($preflightAttempt = 1; $preflightAttempt -le 5; $preflightAttempt++) {
            & $runtimePython -m senpilot.service --config $configPath --check
            if ($LASTEXITCODE -eq 0) { break }
            if ($Update -and $LASTEXITCODE -eq 73 -and $preflightAttempt -lt 5) {
                Write-Output 'Waiting for the previous worker to release its locks.'
                Start-Sleep -Seconds 1
            } else {
                throw 'Local preflight failed. The task was not registered or updated.'
            }
        }
    } finally {
        Pop-Location
    }
    if ($Update) {
        Set-ScheduledTask -TaskName $TaskName -Action $action | Out-Null
    } else {
        Register-ScheduledTask -TaskName $TaskName -InputObject $task | Out-Null
    }
    if ($Start) { Start-ScheduledTask -TaskName $TaskName }
}
