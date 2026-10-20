# Type a message into another seat's Windows Terminal tab and press Enter,
# so an idle AI window (Grok, Codex, Claude) actually receives it.
#   scripts\nudge.ps1 -Tab "Quill-12" -Text "Read the newest Sorrel-12 comment in Q and do it."
# -Tab matches part of the tab title. Returns to the tab that was selected before.
param(
    [Parameter(Mandatory)] [string]$Tab,
    [Parameter(Mandatory)] [string]$Text,
    [switch]$NoEnter
)
# Phil's rule: only wake an AI that still has more than 15% of its usage left.
$ai = @('claude', 'codex', 'grok', 'gemini') | Where-Object { $Tab -match $_ } | Select-Object -First 1
if (-not $ai) {
    $ai = switch -Regex ($Tab) { 'Sorrel|Wren|Ledger|Spool|Tally' { 'claude' } 'Lantern|Alder|Juniper' { 'codex' }
                                 'Quill|Nimbus' { 'grok' } default { $null } }
}
if (-not $ai) { Write-Error "Can't tell which AI '$Tab' is; name it in -Tab (e.g. 'Quill-12 GROK')"; exit 1 }
$line = megazword plan 2>&1 | Where-Object { "$_" -match "^\s*\d+\.\s+$ai\s" } | Select-Object -First 1
$left = if ("$line" -match '(\d+)% left') { [int]$Matches[1] } else { 0 }
if ($left -le 15) { "not nudged: $ai has $left% left (needs more than 15%). Plan line: $line"; exit 2 }

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
$ae = [System.Windows.Automation.AutomationElement]
$tree = [System.Windows.Automation.TreeScope]
$cond = [System.Windows.Automation.Condition]::TrueCondition

$tabType = New-Object System.Windows.Automation.PropertyCondition(
    $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::TabItem)
$target = $null; $window = $null; $previous = $null
foreach ($p in Get-Process WindowsTerminal -ErrorAction SilentlyContinue) {
    if ($p.MainWindowHandle -eq 0) { continue }
    $w = $ae::FromHandle($p.MainWindowHandle)
    foreach ($t in $w.FindAll($tree::Descendants, $tabType)) {
        $sel = $t.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        if ($sel.Current.IsSelected) { $previous = $t }
        if ($t.Current.Name -like "*$Tab*") { $target = $t; $window = $p }
    }
    if ($target) { break }
}
if (-not $target) { Write-Error "No Windows Terminal tab matching '$Tab'"; exit 1 }

$target.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
$shell = New-Object -ComObject WScript.Shell
[void]$shell.AppActivate($window.Id)
Start-Sleep -Milliseconds 600
# SendKeys treats + ^ % ~ ( ) { } [ ] as commands; brace them so they type literally.
$safe = [regex]::Replace($Text, '[+^%~(){}\[\]]', '{$0}')
[System.Windows.Forms.SendKeys]::SendWait($safe)
Start-Sleep -Milliseconds 300
if (-not $NoEnter) { [System.Windows.Forms.SendKeys]::SendWait('{ENTER}') }
Start-Sleep -Milliseconds 300
if ($previous -and $previous -ne $target) {
    $previous.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
}
"nudged: $($target.Current.Name)"
