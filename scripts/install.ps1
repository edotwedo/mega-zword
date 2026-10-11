# Install Mega Zword for this Windows user from this checkout.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Add-UserPath([string]$directory) {
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @($current -split ';' | Where-Object { $_ })
    if (-not ($parts | Where-Object { $_.TrimEnd('\') -ieq $directory.TrimEnd('\') })) {
        [Environment]::SetEnvironmentVariable('Path', (($parts + $directory) -join ';'), 'User')
    }
    if (-not (($env:Path -split ';') | Where-Object { $_.TrimEnd('\') -ieq $directory.TrimEnd('\') })) {
        $env:Path += ";$directory"
    }
}

$pipx = Get-Command pipx -ErrorAction SilentlyContinue
if ($pipx) {
    & $pipx.Source install --force -e $repo
    if ($LASTEXITCODE -ne 0) { throw 'pipx install failed' }
    $bin = if ($env:PIPX_BIN_DIR) { $env:PIPX_BIN_DIR } else { Join-Path $HOME '.local\bin' }
    Add-UserPath $bin
    $doctor = Join-Path $bin 'megazword.exe'
    if (-not (Test-Path $doctor)) {
        $command = Get-Command megazword -ErrorAction Stop
        $doctor = $command.Source
    }
} else {
    $venv = Join-Path $repo '.venv'
    $python = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $python)) {
        $basePython = (Get-Command python -ErrorAction Stop).Source
        & $basePython -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv' }
    }
    & $python -m pip install -e $repo
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
    $bin = Join-Path $venv 'Scripts'
    Add-UserPath $bin
    $doctor = Join-Path $bin 'megazword.exe'
}

& $doctor doctor
exit $LASTEXITCODE
