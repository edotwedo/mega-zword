# Quiet helpers, five-minute metadata snapshots, and one-click local shortcuts.
param([Parameter(Mandatory)][string]$Python)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$entry = Join-Path $PSScriptRoot 'workspace_entry.pyw'
$windowless = Join-Path (Split-Path $Python -Parent) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $windowless)) { throw 'pythonw.exe is required' }
$shell = New-Object -ComObject WScript.Shell
function Shortcut([string]$folder, [string]$name, [string]$action) {
    $link = $shell.CreateShortcut((Join-Path $folder "$name.lnk"))
    $link.TargetPath = $windowless
    $link.Arguments = "`"$entry`" $action"
    $link.WorkingDirectory = $repo
    $link.Description = $name
    $link.Save()
}
$desktop = [Environment]::GetFolderPath('Desktop')
Shortcut $desktop 'Restore Hive' 'restore'
Shortcut $desktop 'Catch me up - terminal' 'catch-up'
Shortcut $desktop 'Enroll my face' 'enroll'
Shortcut ([Environment]::GetFolderPath('Startup')) 'Hive owner camera' 'watch'
# Preserve the older Hive-resume launcher; the new Restore Hive shortcut is silent.
$env:PYTHONPATH = Join-Path $repo 'src'
& $Python -c 'from megazword.workspace import home, import_legacy; p=home().parent/"hive-resume.ps1"; print("Imported",import_legacy(home(),p),"saved launcher seats") if p.exists() else None'
if ($LASTEXITCODE -ne 0) { throw 'Could not import the existing launcher' }
$action = New-ScheduledTaskAction -Execute $windowless -Argument "`"$entry`" snapshot" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'MegaZword-WorkspaceSnapshot' -Action $action -Trigger $trigger -Settings $settings -Description 'Local session IDs and folders only; no AI calls or console windows.' -Force | Out-Null
& $Python $entry snapshot
if ($LASTEXITCODE -ne 0) { throw 'Initial snapshot failed; inspect ~/.megazword/workspace/last-error.json' }
Write-Output 'Installed Restore Hive, Catch me up - terminal, Enroll my face, and quiet five-minute snapshots.'
