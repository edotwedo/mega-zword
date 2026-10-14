# Persistent free HTTP seats: ONE desktop, ONE Terminal window, a tab per seat.
# Does not open Claude/Codex/Grok. Does not start Night Shift. Does not create desktops.
#   pwsh -File scripts\free_floor.ps1
param(
    [string[]]$Seats = @("groq", "cloudflare", "zai", "gemini-api", "mistral")
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $env:USERPROFILE "mega-zword\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "missing $py" }
$src = Join-Path $root "src"

$parts = foreach ($name in $Seats) {
    $cmd = "`$env:PYTHONPATH='$src'; `$env:MEGAZWORD_SEAT='$name'; & '$py' -m megazword chat -m $name"
    "new-tab --title `"MZ $name`" -d `"$root`" pwsh -NoExit -Command `"$cmd`""
}
$wt = ($parts -join " ; ")
Start-Process wt.exe -ArgumentList "--title `"MZ free floor`" --suppressApplicationTitle $wt"
"opened one Terminal on this desktop with tabs: $($Seats -join ', ')."
