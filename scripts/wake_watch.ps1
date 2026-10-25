# Always-on watcher: when Phil posts, start the conductor's turn now instead of at the next
# scheduled beat. No model calls while idle - it asks `megazword wake` once per interval and
# that is a single HTTP GET.
#
#   scripts\wake_watch.ps1                 # watch, wake the tab whose title matches -Tab
#   scripts\wake_watch.ps1 -Once -DryRun   # print what it would do and exit
#
# It is deliberately quiet: no output unless it actually wakes someone, so a scheduled task
# leaves no log noise.
param(
    [int]$Interval = 60,
    [string]$Tab = 'cinder-21',
    [switch]$Once,
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
Add-Type -Namespace W -Name Idle -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
[DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
[DllImport("kernel32.dll")] public static extern uint GetTickCount();
'@

function Seconds-Since-Input {
    $info = New-Object W.Idle+LASTINPUTINFO
    $info.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($info)
    [void][W.Idle]::GetLastInputInfo([ref]$info)
    return [math]::Round((([W.Idle]::GetTickCount() - $info.dwTime) / 1000), 0)
}

function Send-ToTab([string]$match, [string]$text) {
    $ae = [System.Windows.Automation.AutomationElement]
    $scope = [System.Windows.Automation.TreeScope]
    $tabType = New-Object System.Windows.Automation.PropertyCondition(
        $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::TabItem)
    $target = $null; $window = $null; $previous = $null
    foreach ($p in Get-Process WindowsTerminal -ErrorAction SilentlyContinue) {
        if ($p.MainWindowHandle -eq 0) { continue }
        $w = $ae::FromHandle($p.MainWindowHandle)
        foreach ($t in $w.FindAll($scope::Descendants, $tabType)) {
            $sel = $t.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
            if ($sel.Current.IsSelected) { $previous = $t }
            if ($t.Current.Name -like "*$match*") { $target = $t; $window = $p }
        }
        if ($target) { break }
    }
    if (-not $target) { return $false }
    try {
        $target.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        $shell = New-Object -ComObject WScript.Shell
        if (-not $shell.AppActivate($window.Id)) { return $false }
        Start-Sleep -Milliseconds 700
        $safe = [regex]::Replace($text, '[+^%~(){}\[\]]', '{$0}')
        [System.Windows.Forms.SendKeys]::SendWait($safe)
        Start-Sleep -Milliseconds 300
        [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
        Start-Sleep -Milliseconds 300
        return $true
    } catch {
        Write-Warning "wake delivery failed; leaving message pending"
        return $false
    } finally {
        if ($previous -and $previous -ne $target) {
            try {
                $previous.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
            } catch {
                Write-Warning 'wake tab restoration unavailable; continuing watcher'
            }
        }
    }
}

while ($true) {
    $raw = @(& megazword wake --peek --json 2>$null)
    $wakeExit = $LASTEXITCODE
    $notice = $null
    if ($wakeExit -eq 0 -and $raw.Count -eq 1) {
        try { $notice = $raw[0] | ConvertFrom-Json -ErrorAction Stop } catch { }
    }
    if ($notice -and ($notice.through -is [int] -or $notice.through -is [long]) -and $notice.through -gt 0 -and
            $notice.line -is [string] -and $notice.line.StartsWith('Cinder-21: Phil posted in the hive') -and
            $notice.line -notmatch '[\r\n]') {
        $line = $notice.line
        # Never type into the machine while Phil is using it: the wake is important, but not
        # more important than the keystrokes he is half-way through.
        $idle = Seconds-Since-Input
        if ($DryRun) {
            "would wake: $line (idle ${idle}s)"
        } elseif ($idle -lt 20) {
            "wake held: Phil is typing (idle ${idle}s)"
        } else {
            $sent = Send-ToTab $Tab $line
            if ($sent) {
                & megazword wake --ack $notice.through
                if ($LASTEXITCODE -ne 0) { Write-Warning 'wake sent, but acknowledgement failed; it may be sent again' }
            }
            "wake $(if ($sent) { 'sent' } else { "not delivered to '$Tab'; still pending" }): $line"
        }
    }
    if ($Once) { break }
    Start-Sleep -Seconds $Interval
}
