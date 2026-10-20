# Repair only Mega Zword's existing Sentinel task action. Triggers, identity,
# arguments and other settings are retained. Default: inspect, without changes.
# UseWorktreeSource loads this checkout's fixes without editing a shared install.
param([switch]$Apply, [switch]$UseWorktreeSource)
$ErrorActionPreference = 'Stop'
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'src'
if ($UseWorktreeSource -and -not (Test-Path (Join-Path $source 'megazword/sentinel.py'))) {
    throw "Missing Sentinel source: $source"
}
foreach ($taskName in @('MegaZword-Sentinel', 'MegaZword-Sentinel-Logon')) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) { continue }
    $actions = @($task.Actions)
    if ($actions.Count -ne 1) { throw "Refusing multi-action task: $taskName" }
    $action = $actions[0]
    $exe = $action.Execute.Trim('"')
    if ([IO.Path]::GetFileName($exe) -notin @('python.exe', 'pythonw.exe') -or
        $action.Arguments -notmatch '^\s*-m\s+megazword\.cli\s+sentinel\s+check\s*$') {
        throw "Refusing an unexpected action on $taskName"
    }
    $windowless = Join-Path ([IO.Path]::GetDirectoryName($exe)) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $windowless -PathType Leaf)) {
        throw "Windowless Python is missing: $windowless"
    }
    if (-not $Apply) {
        Write-Output "$taskName would switch to $windowless (run with -Apply)."
        continue
    }
    $options = @{Execute=$windowless; Argument=$action.Arguments}
    if ($action.WorkingDirectory) { $options.WorkingDirectory=$action.WorkingDirectory }
    if ($UseWorktreeSource) { $options.WorkingDirectory=$source }
    $replacement = New-ScheduledTaskAction @options
    Set-ScheduledTask -TaskName $taskName -TaskPath $task.TaskPath -Action $replacement | Out-Null
    $verified = Get-ScheduledTask -TaskName $taskName -TaskPath $task.TaskPath
    if ($verified.Actions.Execute.Trim('"') -ine $windowless) {
        throw "Task verification failed: $taskName"
    }
    if ($UseWorktreeSource -and $verified.Actions.WorkingDirectory -ine $source) {
        throw "Task source verification failed: $taskName"
    }
    Write-Output "$taskName now uses windowless Python."
}
