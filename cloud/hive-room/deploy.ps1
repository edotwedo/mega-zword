param(
    [string[]]$Seats = @('phil', 'beacon-17', 'cirrus-17'),
    [string]$WorkerName = 'megazword-hive-room',
    [string]$DatabaseId = ''
)
# Phil runs this script. Bots must never execute it.
$ErrorActionPreference = 'Stop'
if ($WorkerName -notmatch '^[a-z0-9-]{1,63}$') { throw 'Use a lowercase Worker name.' }
if (!$Seats.Count -or ($Seats | Select-Object -Unique).Count -ne $Seats.Count) { throw 'Supply unique seat names.' }
foreach ($seatName in $Seats) {
    if ($seatName -cnotmatch '^[a-z0-9-]{1,64}$') { throw 'Seats must use lowercase letters, digits and hyphens.' }
}
if ($DatabaseId -and $DatabaseId -notmatch '^[a-fA-F0-9-]{36}$') { throw 'Invalid D1 database ID.' }
Push-Location $PSScriptRoot
try {
    # Wrangler's config contains only a resource ID, never credentials.
    if (!$DatabaseId) {
        if (Test-Path -LiteralPath 'wrangler.local.json') { throw 'Config already exists. Pass its DatabaseId explicitly to reuse storage.' }
        $created = & npx --yes wrangler@4 d1 create "$WorkerName-db" 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { throw 'D1 creation failed. Check Wrangler login/account, then retry.' }
        $found = [regex]::Match($created, '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
        if (!$found.Success) { throw 'D1 created but its ID could not be parsed. Read its ID in the dashboard and rerun with -DatabaseId.' }
        $DatabaseId = $found.Value
    }
    $cfg = @{ name=$WorkerName; main='index.js'; compatibility_date='2026-10-17';
        workers_dev=$true; d1_databases=@(@{binding='DB'; database_name="$WorkerName-db"; database_id=$DatabaseId}) }
    $cfg | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath 'wrangler.local.json' -Encoding UTF8
    & npx --yes wrangler@4 d1 execute DB --remote --file schema.sql --config wrangler.local.json
    if ($LASTEXITCODE -ne 0) { throw 'Schema failed; deployment stopped.' }
    & npx --yes wrangler@4 deploy --config wrangler.local.json
    if ($LASTEXITCODE -ne 0) { throw 'Deployment failed; no tokens generated.' }
    $hashes = @{}
    $issued = @{}
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        foreach ($seatName in $Seats) {
            $bytes = New-Object byte[] 32
            $rng.GetBytes($bytes)
            $seatToken = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
            $hex = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($seatToken))).Replace('-','').ToLowerInvariant()
            $hashes[$hex] = $seatName
            $issued[$seatName] = $seatToken
            [Array]::Clear($bytes, 0, $bytes.Length)
        }
        # Only hashes travel through stdin; raw seat tokens stay in memory.
        $hashes | ConvertTo-Json -Compress | & npx --yes wrangler@4 secret put SEAT_TOKENS --config wrangler.local.json
        if ($LASTEXITCODE -ne 0) { throw 'Secret upload failed. Tokens were not printed; rerun with -DatabaseId to rotate them.' }
        Write-Host 'Copy each token directly into its seat secret settings. These appear once:'
        foreach ($seatName in $Seats) { Write-Host "$seatName : $($issued[$seatName])" }
    } finally {
        $rng.Dispose(); $sha.Dispose(); $issued.Clear(); $hashes.Clear(); $seatToken = $null
    }
    Write-Host 'Use the HTTPS workers.dev URL printed by Wrangler as HIVE_ROOM_URL. Test PC/cloud exchange manually.'
} finally { Pop-Location }
