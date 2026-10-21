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
    [int]$Interval = 30,
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
    $target.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    $shell = New-Object -ComObject WScript.Shell
    [void]$shell.Activate($window.Id)
    Start-Sleep -Milliseconds 700
    $safe = [regex]::Replace($text, '[+^%~(){}\[\]]', '{$0}')
    [System.Windows.Forms.SendKeys]::SendWait($safe)
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    Start-Sleep -Milliseconds 300
    if ($previous -and $previous -ne $target) {
        $previous.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    }
    return $true
}

while ($true) {
    $line = (& megazword wake 2>$null | Select-Object -First 1)
    if ($line) {
        # Never type into the machine while Phil is using it: the wake is important, but not
        # more important than the keystrokes he is half-way through.
        $idle = Seconds-Since-Input
        if ($DryRun) {
            "would wake: $line (idle ${idle}s)"
        } elseif ($idle -lt 20) {
            "wake held: Phil is typing (idle ${idle}s)"
        } else {
            $sent = Send-ToTab $Tab $line
            "wake $(if ($sent) { 'sent' } else { "not sent: no tab matching '$Tab'" }): $line"
        }
    }
    if ($Once) { break }
    Start-Sleep -Seconds $Interval
}
