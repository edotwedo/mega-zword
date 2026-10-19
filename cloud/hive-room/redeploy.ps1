# Code-only redeploy of the LIVE Hive Worker, plus the two ntfy topics.
# Deployments are authorized (Phil, 2026-10-18). This does NOT rotate seat tokens
# and does NOT touch D1 data, so existing connectors keep working.
#
# Run from cloud/hive-room after `git pull`:
#   powershell -ExecutionPolicy Bypass -File .\redeploy.ps1
#
# Needs the wrangler.local.json that Phil's original deploy created (it holds the
# D1 database id). If wrangler says "No access to the specified service", run
# `npx wrangler@4 login` and sign in as the account that owns the Worker.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (!(Test-Path -LiteralPath 'wrangler.local.json')) {
        throw 'wrangler.local.json missing. Run deploy.ps1 once (or restore the file) first.'
    }
    # A stale CLOUDFLARE_API_TOKEN in the environment blocks OAuth login AND is used
    # instead of it, but it lacks access to this Worker (error 9109 / "No access to
    # the specified service"). Clear both for this run so OAuth is used.
    $env:CLOUDFLARE_API_TOKEN = $null
    $env:CLOUDFLARE_ACCOUNT_ID = $null
    Write-Host 'Signing in to Cloudflare (opens a browser if needed)...'
    npx --yes wrangler@4 login
    Write-Host 'Deploying Worker code (no token rotation)...'
    npx --yes wrangler@4 deploy --config wrangler.local.json
    if ($LASTEXITCODE -ne 0) { throw 'Deploy failed; nothing changed.' }

    $alphabet = (48..57) + (97..122)
    function New-Topic([string]$prefix) {
        $suffix = -join (1..6 | ForEach-Object { [char]($alphabet | Get-Random) })
        return "$prefix-$suffix"
    }
    $pc = New-Topic 'megazword-hive-pc'
    $phone = New-Topic 'megazword-hive-phone'
    $pc | npx --yes wrangler@4 secret put NTFY_PC_TOPIC --config wrangler.local.json
    $phone | npx --yes wrangler@4 secret put NTFY_PHONE_TOPIC --config wrangler.local.json

    Write-Host ''
    Write-Host 'Deployed. Keep these ntfy topics (they are the wake channel):'
    Write-Host "  PC seats listen on $pc"
    Write-Host "    -> run:  megazword room wait --topic $pc,megazword-hive-seat-<designation>"
    Write-Host "  Phone alerts on $phone"
    Write-Host ''
    Write-Host 'Phone app: https://megazword-hive-room.phone-liaison.workers.dev/app/<key>'
    Write-Host '  Open it in Chrome, then Add to Home Screen. Any valid seat key works.'
    Write-Host '  For a broadcast to wake the PC, the key must be the phone lane or a PC lane.'
} finally {
    Pop-Location
}
