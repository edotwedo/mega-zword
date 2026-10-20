param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$jobId = '2026-10-15-2343'
$plannedStart = [datetime]::ParseExact('2026-10-15 23:43:00', 'yyyy-MM-dd HH:mm:ss', [Globalization.CultureInfo]::InvariantCulture)
$latestStart = $plannedStart.AddMinutes(30)
$maxRuntime = [timespan]::FromMinutes(15)
$model = 'tencent-kimi-k2.7-code'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = 'C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe'
$stateDir = Join-Path $env:LOCALAPPDATA "MegaZword\FreeToolsContinuation\$jobId"
$statusPath = Join-Path $stateDir 'status.json'
$logPath = Join-Path $stateDir 'run.log'
$stopPath = Join-Path $stateDir 'STOP'

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

function Write-Heartbeat([string]$State, [string]$Detail, [Nullable[int]]$ExitCode = $null) {
    $status = [ordered]@{
        job = $jobId
        state = $State
        model = $model
        free_only = $true
        planned_start_local = '2026-10-15 23:43:00'
        updated_utc = [datetime]::UtcNow.ToString('o')
        process_id = if ($script:child -and -not $script:child.HasExited) { $script:child.Id } else { $null }
        exit_code = $ExitCode
        detail = $Detail
        log = $logPath
    }
    $tmp = "$statusPath.tmp"
    [IO.File]::WriteAllText($tmp, ($status | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tmp -Destination $statusPath -Force
}

if (Test-Path -LiteralPath $stopPath) {
    Write-Heartbeat 'stopped' 'STOP marker was present before launch.'
    exit 0
}
if ($DryRun) {
    Write-Heartbeat 'dry-run-ok' 'Task script, worktree path, Python path, model, and stop/status paths were resolved. No model was called.'
    exit 0
}

$now = Get-Date
if ($now -lt $plannedStart) {
    Write-Heartbeat 'skipped-early' "Task started before its scheduled time ($($now.ToString('o')))."
    exit 0
}
if ($now -gt $latestStart) {
    Write-Heartbeat 'missed-window' "Task started after the 30-minute start window ($($now.ToString('o')))."
    exit 0
}
if (-not (Test-Path -LiteralPath $python)) {
    Write-Heartbeat 'failed' "Configured Python runtime is missing: $python"
    exit 2
}

$prompt = @'
Continue Mega Zword's tool-access work. You are the free Tencent coding model selected by Phil. Inspect the actual current code and project docs before editing. Implement one small, safe capability that lets the free API coding agent retrieve a user-specified public HTTPS URL as bounded text, so it can inspect public documentation and URLs. Enforce HTTPS only; reject credentials in URLs, localhost/private/link-local/reserved IPs (including after DNS resolution), and unsafe redirects; cap response bytes and time; accept only text/HTML/JSON; strip scripts/styles and return readable text where practical. Never send cookies, tokens, environment values, local files, or authenticated browser state. Add focused tests for the security boundaries and update the agent-access docs. If the code architecture makes a safe implementation larger than one focused step, write a concrete design and stop without a risky partial implementation.

Use only the tools actually provided to you. Run the focused tests with your run_tests tool. Do not add shell, arbitrary filesystem access, browser automation, cloud-console login, account/API-key/billing changes, messages, Git operations, commits, or pushes. Do not read, edit, stage, or commit CODEX_JOB.md. Do not claim access you do not have. This run is free-only and limited to this one bounded task. Finish with exact files changed, tests run/results, remaining risks, and the next step.
'@

$startInfo = [Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $python
$startInfo.Arguments = '-m megazword run --edit --model tencent-kimi-k2.7-code --free-only --project mega-zword --context'
$startInfo.WorkingDirectory = $root
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardInput = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.EnvironmentVariables['PYTHONPATH'] = Join-Path $root 'src'
$startInfo.EnvironmentVariables['PYTHONUTF8'] = '1'
$startInfo.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
$script:child = [Diagnostics.Process]::new()
$script:child.StartInfo = $startInfo

try {
    [IO.File]::WriteAllText($logPath, "Started $($now.ToString('o')); model=$model; free_only=true`r`n", [Text.UTF8Encoding]::new($false))
    if (-not $script:child.Start()) { throw 'Could not start Mega Zword.' }
    $stdoutTask = $script:child.StandardOutput.ReadToEndAsync()
    $stderrTask = $script:child.StandardError.ReadToEndAsync()
    $script:child.StandardInput.WriteLine($prompt)
    $script:child.StandardInput.Close()
    $startedAt = [datetime]::UtcNow
    Write-Heartbeat 'running' 'Free-only Tencent coding run started; no UI windows are opened.'

    while (-not $script:child.WaitForExit(10000)) {
        if (Test-Path -LiteralPath $stopPath) {
            Write-Heartbeat 'stopping' 'STOP marker received; terminating the model run.'
            & taskkill.exe /PID $script:child.Id /T /F 2>$null | Out-Null
            $script:child.WaitForExit()
            break
        }
        if (([datetime]::UtcNow - $startedAt) -ge $maxRuntime) {
            Write-Heartbeat 'stopping' '15-minute safety timeout reached; terminating the model run.'
            & taskkill.exe /PID $script:child.Id /T /F 2>$null | Out-Null
            $script:child.WaitForExit()
            break
        }
        Write-Heartbeat 'running' 'Model run is active; the heartbeat updates every 10 seconds.'
    }

    $script:child.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $log = "Started $($now.ToString('o')); finished $([datetime]::Now.ToString('o')); model=$model; free_only=true; exit=$($script:child.ExitCode)`r`n`r`n--- stdout ---`r`n$stdout`r`n--- stderr ---`r`n$stderr"
    [IO.File]::WriteAllText($logPath, $log, [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $stopPath) {
        Write-Heartbeat 'stopped' 'Run stopped by STOP marker.' $script:child.ExitCode
    } elseif ($script:child.ExitCode -eq 0) {
        Write-Heartbeat 'completed' 'Model run exited successfully.' $script:child.ExitCode
    } else {
        Write-Heartbeat 'failed' 'Model run exited with an error; see run.log.' $script:child.ExitCode
    }
    exit $script:child.ExitCode
} catch {
    [IO.File]::AppendAllText($logPath, "`r`nLauncher error: $($_.Exception.Message)`r`n", [Text.UTF8Encoding]::new($false))
    Write-Heartbeat 'failed' 'Launcher error; see run.log.' 1
    exit 1
} finally {
    if ($script:child) { $script:child.Dispose() }
}
