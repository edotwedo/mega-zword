# Code-only redeploy of the LIVE Hive Worker. Preserve existing ntfy topics.
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
    if ($LASTEXITCODE -ne 0) { throw 'Cloudflare login failed; deploy stopped.' }
    Write-Host 'Deploying Worker code (no token rotation)...'
    npx --yes wrangler@4 deploy --config wrangler.local.json
    if ($LASTEXITCODE -ne 0) { throw 'Deploy failed; nothing changed.' }

    Write-Host ''
    Write-Host 'Deployed. Existing notification topics and seat tokens were preserved.'
    Write-Host 'PC seats keep listening on their configured topic; no reconnect is needed.'
    Write-Host ''
    Write-Host 'Phone app: https://megazword-hive-room.phone-liaison.workers.dev/app/<key>'
    Write-Host '  Open it in Chrome, then Add to Home Screen. Any valid seat key works.'
    Write-Host '  For a broadcast to wake the PC, the key must be the phone lane or a PC lane.'
} finally {
    Pop-Location
}
