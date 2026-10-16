param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$designation = 'Testlog-14'
$jobId = '2026-10-16-0500'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$testPython = 'C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe'
$stateDir = Join-Path $env:LOCALAPPDATA "MegaZword\FreeToolsContinuation\$jobId"
$statusPath = Join-Path $stateDir 'status.json'
$stopPath = Join-Path $stateDir 'STOP'
$start = [datetime]::ParseExact('2026-10-16 05:00', 'yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture)
$hardStop = [datetime]::ParseExact('2026-10-16 11:00', 'yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture)
$models = @(
    'tencent-deepseek-v4-pro',
    'tencent-deepseek-v4-flash-vision-exp',
    'tencent-kimi-k3',
    'tencent-glm-5.3',
    'tencent-glm-5.3-flash',
    'tencent-kimi-k2.7-code'
)
$labels = @(
    'Review and finish the previous bounded public-URL tool change. Inspect its source and tests; do not repeat completed work.',
    'Verify the supplied config.py audit findings. Reproduce before changing anything; implement only a material, tested defect.',
    'Verify the audit finding that Tencent route order ignores saved low-quota marks. Make a small tested routing change only if the current source confirms it.',
    'Check the audit claim about 429 cooldowns against free_apis.py, limits.py and tests. This may already be fixed; do not reintroduce a one-hour penalty or change correct behavior.',
    'Inspect the existing free-model catalog and candidate workflow. Improve safe discovery only if a concrete gap remains; never activate a model, create an account/key, enable billing, or call an unverified provider.',
    'Review all morning changes for source evidence, free-only routing, tests and clear limitations. Update the handoff/status with the exact result and next step.'
)
$prompts = @(
@'
Continue Mega Zword's tool-access and free-usage work in this checkout. The separate 11:43 PM Kimi run failed at the 60-step cap without a usable answer or tracked diff; Testlog-14 has since implemented the bounded public-HTTPS fetch in src/megazword/public_fetch.py with tests. Verify the current source and tests, do not duplicate the fetch implementation, then use this slot for one source-grounded audit step from the handoff. Never access local credentials, authenticated pages, cloud consoles, billing or accounts. Do not read or edit CODEX_JOB.md. Update docs/STATUS.md with the exact result and next step.
'@,
@'
Read the audit summary in docs/handoffs/2026-10-16-testlog14-morning-shift.md, then verify its config.py hypotheses against the current source: the __mz_marker__ collision, _statements complexity/diagnostics, no-op write semantics, deferred filelock import, and parse_until units. Reproduce before changing anything. Choose at most one material, demonstrable defect for a focused fix/test; do not rewrite the parser or add unsupported behavior just to match the audit. Do not read or edit CODEX_JOB.md. Update docs/STATUS.md with evidence and the precise next step. The outer runner will run the full test suite and handle local-Gitea commits; do not run git.
'@,
@'
Read the audit summary in docs/handoffs/2026-10-16-testlog14-morning-shift.md. Verify whether Tencent route ordering ignores useful quota marks. Inspect routing.py and free_apis.py. If request_quota_low state can safely influence tencent_first without breaking shared pools or deterministic ordering, implement the smallest fix and focused tests. Otherwise explain exactly why, with file/line evidence, and leave source unchanged. Do not read or edit CODEX_JOB.md. Update docs/STATUS.md with evidence and the precise next step. The outer runner handles tests and local-Gitea commits; do not run git.
'@,
@'
Read the audit summary in docs/handoffs/2026-10-16-testlog14-morning-shift.md. Audit the claim that HTTP 429 rate limits and true quota exhaustion get the same one-hour fallback. Inspect the current APIHTTPError, provider-specific 429 handling, limits.py, and tests. Preserve Retry-After/reset times and do not guess a new cooldown. If current code already distinguishes these correctly, make no code change and report the evidence. If a concrete regression remains, add a focused test and fix only that case. Do not read or edit CODEX_JOB.md. Update docs/STATUS.md. The outer runner handles tests and local-Gitea commits; do not run git.
'@,
@'
Advance Mega Zword's goal of discovering usable no-cost coding capacity. Inspect openrouter_catalog.py, the existing free-test/catalog commands and docs/FREE-MODEL-ROSTER.md. Keep catalog candidates separate from verified/automatic routes. If the bounded public-URL tool exists, use it only on official provider documentation to document a concrete free tool-capable candidate and its limits; do not create accounts/keys, activate models, send inference requests, change billing or add unverified routes. If no concrete safe improvement is supported by evidence, write a short recommendation instead of speculative code. Do not read or edit CODEX_JOB.md. Update docs/STATUS.md. The outer runner handles tests and local-Gitea commits; do not run git.
'@,
@'
Read the audit summary in docs/handoffs/2026-10-16-testlog14-morning-shift.md. Perform a final source-grounded review of the morning changes and Mega Zword's free-only tool-access path. Verify tests and docs match the code, candidate/free/verified states stay distinct, and no paid fallback or secret access was added. Do not make broad changes; fix only a concrete, tested defect. Do not read or edit CODEX_JOB.md. Update docs/STATUS.md and a concise handoff with completed work, tests, blockers, and the next exact step. The outer runner handles tests and local-Gitea commits; do not run git.
'@
)

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

function Save-State([string]$State, [string]$Detail, [int]$Slot = -1, [Nullable[int]]$ExitCode = $null) {
    $data = [ordered]@{
        job = $jobId
        state = $State
        slot = $Slot
        model = if ($Slot -ge 0 -and $Slot -lt $models.Count) { $models[$Slot] } else { $null }
        detail = $Detail
        free_only = $true
        pay_as_you_go_changed = $false
        updated_local = [datetime]::Now.ToString('o')
        exit_code = $ExitCode
        stop_file = $stopPath
    }
    $tmp = "$statusPath.tmp"
    [IO.File]::WriteAllText($tmp, ($data | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tmp -Destination $statusPath -Force
}

function Run-Process([string]$File, [string]$Arguments, [string]$Cwd, [int]$TimeoutSeconds,
                    [string]$InputText = '', [switch]$SanitizeEnv) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $File
    $info.Arguments = $Arguments
    $info.WorkingDirectory = $Cwd
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.EnvironmentVariables['PYTHONUTF8'] = '1'
    $info.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $info.EnvironmentVariables['PYTHONPATH'] = Join-Path $root 'src'
    if ($SanitizeEnv) {
        foreach ($key in @($info.EnvironmentVariables.Keys)) {
            if ($key -match '(_API_KEY|_API_TOKEN|_TOKEN|_SECRET|_PASSWORD)$|^(GH_|GITHUB_)') {
                $info.EnvironmentVariables.Remove($key)
            }
        }
        $info.EnvironmentVariables.Remove('MEGAZWORD_NO_USER_ENV') | Out-Null
        $info.EnvironmentVariables['MEGAZWORD_NO_APP'] = '1'
        $info.EnvironmentVariables['MEGAZWORD_HOME'] = Join-Path $stateDir 'test-home'
        $info.EnvironmentVariables['GIT_TERMINAL_PROMPT'] = '0'
        $info.EnvironmentVariables['GCM_INTERACTIVE'] = 'never'
    }
    $proc = [Diagnostics.Process]::new()
    $proc.StartInfo = $info
    if (-not $proc.Start()) { throw "Could not start $File" }
    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    if ($InputText) { $proc.StandardInput.WriteLine($InputText) }
    $proc.StandardInput.Close()
    $began = [datetime]::UtcNow
    while (-not $proc.WaitForExit(10000)) {
        if (Test-Path -LiteralPath $stopPath) {
            $proc.Kill($true)
            $proc.WaitForExit()
            Save-State 'stopped' 'STOP marker received; child process tree terminated.' $script:slot $proc.ExitCode
            break
        }
        if (([datetime]::UtcNow - $began).TotalSeconds -ge $TimeoutSeconds -or (Get-Date) -ge $hardStop) {
            $proc.Kill($true)
            $proc.WaitForExit()
            break
        }
        Save-State 'running' "Slot $($script:slot + 1)/6; $($labels[$script:slot]); process heartbeat." $script:slot
    }
    $proc.WaitForExit()
    $output = $stdoutTask.GetAwaiter().GetResult()
    $errorText = $stderrTask.GetAwaiter().GetResult()
    $code = $proc.ExitCode
    $proc.Dispose()
    return [pscustomobject]@{ ExitCode = $code; Stdout = $output; Stderr = $errorText }
}

function Git-Out([string[]]$GitArgs) {
    $result = & git -C $root @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git $($GitArgs -join ' ') failed: $($result | Out-String)" }
    return ($result | Out-String).Trim()
}

function Update-Active([string]$Detail) {
    $path = Join-Path $root 'docs\STATUS.md'
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $line = "**Active: $designation (Codex scheduled shift) - $((Get-Date).ToString('yyyy-MM-dd h:mm tt')) PT. $Detail**"
    $updated = [regex]::Replace($text, '(?m)^\*\*Active:.*\*\*$', [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line }, 1)
    if ($updated -eq $text) { throw 'Could not find the Active line in docs/STATUS.md.' }
    [IO.File]::WriteAllText($path, $updated, [Text.UTF8Encoding]::new($false))
}

function Publish-Active([string]$Detail, [int]$Slot) {
    Update-Active $Detail
    & git -C $root add -- docs/STATUS.md | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage the scheduled-slot claim.' }
    & git -C $root diff --cached --check | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Scheduled-slot claim diff check failed.' }
    & git -C $root commit -m "Claim Testlog-14 morning slot $($Slot + 1)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not commit the scheduled-slot claim.' }
    & git -C $root push origin HEAD:main | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not publish the scheduled-slot claim to local Gitea.' }
}

function Release-Active([string]$Detail) {
    $path = Join-Path $root 'docs\STATUS.md'
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $updated = [regex]::Replace($text, '(?m)^\*\*Active:.*\*\*$', '**Active: none.**', 1)
    $note = "**Morning free-model shift (Testlog-14):** $Detail`r`n"
    $updated = [regex]::Replace($updated, '(?m)^\*\*Active: none\.\*\*$', ('$0' + "`r`n" + $note), 1)
    [IO.File]::WriteAllText($path, $updated, [Text.UTF8Encoding]::new($false))
}

function Publish-Failure([string]$Detail) {
    Release-Active "Morning automation stopped; inspect local status/logs before resuming. $Detail"
    & git -C $root reset --mixed HEAD | Out-Null
    if ($LASTEXITCODE -ne 0) { return }
    & git -C $root add -- docs/STATUS.md | Out-Null
    if ($LASTEXITCODE -ne 0) { return }
    & git -C $root diff --cached --check | Out-Null
    if ($LASTEXITCODE -ne 0) { return }
    $staged = (& git -C $root diff --cached -U0) -join "`n"
    if ($staged -match '(?im)^\+[^\r\n]*(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|AKID[A-Za-z0-9]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY)') { return }
    & git -C $root commit -m 'Record blocked morning free-model step' | Out-Null
    if ($LASTEXITCODE -ne 0) { return }
    & git -C $root push origin HEAD:main | Out-Null
}

function Check-PathsAndCommit([int]$Slot) {
    $changed = @(& git -C $root status --short --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect git status.' }
    $paths = @()
    foreach ($line in $changed) {
        if ($line.Length -lt 4) { continue }
        $path = $line.Substring(3).Trim()
        if ($path -eq 'CODEX_JOB.md') { continue }
        if ($path -notmatch '^(src/megazword/|tests/|docs/)') {
            throw "Changed path is outside the overnight allowlist: $path"
        }
        $paths += $path
    }
    if (-not $paths.Count) { return 'No source changes to commit.' }

    foreach ($path in ($paths | Select-Object -Unique)) {
        & git -C $root add -- $path | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not stage $path" }
    }
    $diff = (& git -C $root diff --cached -U0) -join "`n"
    if ($diff -match '(?im)^\+[^\r\n]*(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|AKID[A-Za-z0-9]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY)') {
        throw 'Secret-pattern guard refused the staged change.'
    }
    & git -C $root diff --cached --check
    if ($LASTEXITCODE -ne 0) { throw 'Staged diff check failed.' }
    $message = "Morning free-model step $($Slot + 1): $($labels[$Slot].Split('.')[0])"
    & git -C $root commit -m $message | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Commit failed.' }
    & git -C $root push origin HEAD:main
    if ($LASTEXITCODE -ne 0) { throw 'Local Gitea push failed; commit remains on this seat branch.' }
    return "Committed and pushed validated step $($Slot + 1) to local Gitea origin/main."
}

if ($DryRun) {
    if (-not (Test-Path -LiteralPath $python)) { throw "Python runtime missing: $python" }
    if (-not (Test-Path -LiteralPath $testPython)) { throw "Test runtime missing: $testPython" }
    $origin = (& git -C $root remote get-url origin).Trim()
    if ($origin -notmatch '^https?://127\.0\.0\.1:3000/') { throw "origin is not local Gitea: $origin" }
    Save-State 'dry-run-ok' 'Six hourly free-only steps, hard stop 11:00 PT, hidden process, local Gitea only; no model calls.'
    exit 0
}

$now = Get-Date
if ($now -lt $start -or $now -ge $hardStop) { Save-State 'outside-window' "Not in the 5:00-11:00 AM PT work window: $($now.ToString('o'))"; exit 0 }
if (Test-Path -LiteralPath $stopPath) { Save-State 'stopped' 'STOP marker was present before launch.'; exit 0 }
if (-not (Test-Path -LiteralPath $python)) { Save-State 'blocked' "Python runtime missing: $python"; exit 2 }

$script:slot = [Math]::Min(5, [Math]::Floor(($now - $start).TotalHours))
$slotStart = $start.AddHours($script:slot)
if ($now -ge $slotStart.AddMinutes(45)) { Save-State 'missed-slot' "Slot $($script:slot + 1) started more than 45 minutes late." $script:slot; exit 0 }
if (Test-Path $statusPath) {
    $previousState = Get-Content -Raw $statusPath | ConvertFrom-Json
    if ($previousState.state -in @('blocked', 'stopped')) { exit 0 }
    if ($previousState.state -eq 'completed' -and $previousState.slot -eq $script:slot) { exit 0 }
    if ($previousState.state -eq 'running' -and $previousState.slot -ne $script:slot) {
        Save-State 'blocked' "Previous slot $($previousState.slot + 1) did not finish; inspect its log before continuing." $script:slot
        exit 0
    }
}

try {
    $origin = Git-Out @('remote', 'get-url', 'origin')
    if ($origin -notmatch '^https?://127\.0\.0\.1:3000/') { throw "origin is not local Gitea: $origin" }
    & git -C $root diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Staged changes already exist; refusing to include them in scheduled commits.' }
    Git-Out @('fetch', 'origin') | Out-Null
    $mainStatus = Git-Out @('show', 'origin/main:docs/STATUS.md')
    $active = [regex]::Match($mainStatus, '(?m)^\*\*Active:\s*([^*]+)\*\*').Groups[1].Value.Trim()
    if ($active -and $active -notmatch '^(none|Testlog-14\b)') {
        Save-State 'blocked' "Another worker owns Mega Zword: $active" $script:slot
        exit 0
    }
    Git-Out @('pull', '--rebase', 'origin', 'main') | Out-Null
    Publish-Active "Running hidden free-only work, slot $($script:slot + 1)/6. Hard stop 11:00 AM PT; paid fallback excluded." $script:slot

    $priorStatusPath = Join-Path $env:LOCALAPPDATA 'MegaZword\FreeToolsContinuation\2026-10-15-2343\status.json'
    $priorSummary = 'No previous-run status file.'
    if (Test-Path $priorStatusPath) {
        $prior = Get-Content -Raw $priorStatusPath | ConvertFrom-Json
        $priorSummary = "state=$($prior.state); detail=$($prior.detail); exit=$($prior.exit_code)"
    }
    $prompt = $prompts[$script:slot] + "`n`nPrior 11:43 PM public-URL step: $priorSummary`n`nDo not run git or access CODEX_JOB.md."
    $model = $models[$script:slot]
    Save-State 'running' "Starting slot $($script:slot + 1)/6: $($labels[$script:slot])." $script:slot
    $args = "-m megazword run --edit --model $model --free-only --project mega-zword --context"
    $result = Run-Process $python $args $root 900 $prompt
    $slotLog = Join-Path $stateDir ("slot-{0}-{1}.log" -f ($script:slot + 1), $model)
    $log = "model=$model`nfree_only=true`nexit=$($result.ExitCode)`n`n--- stdout ---`n$($result.Stdout)`n`n--- stderr ---`n$($result.Stderr)"
    [IO.File]::WriteAllText($slotLog, $log, [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $stopPath) { Save-State 'stopped' 'STOP marker received; no later slots will run.' $script:slot $result.ExitCode; Publish-Failure 'Phil stopped the morning automation; inspect local logs before resuming.'; exit 0 }
    if ($result.ExitCode -ne 0) { throw "Mega Zword run failed with exit $($result.ExitCode); see $slotLog" }

    $sourceChanges = @(& git -C $root status --short --untracked-files=all | Where-Object { $_ -match '^(\s?[MARCDU?]{1,2}\s+)(src/megazword/|tests/)' })
    if ($sourceChanges.Count) {
        Save-State 'testing' "Running full test suite after slot $($script:slot + 1)." $script:slot
        $testInfo = Run-Process $testPython '-m pytest -q --tb=short' $root 900 '' -SanitizeEnv
        $testLog = Join-Path $stateDir ("slot-{0}-tests.log" -f ($script:slot + 1))
        [IO.File]::WriteAllText($testLog, "exit=$($testInfo.ExitCode)`n$($testInfo.Stdout)`n$($testInfo.Stderr)", [Text.UTF8Encoding]::new($false))
        if ($testInfo.ExitCode -ne 0) { throw "Full test suite failed; see $testLog" }
    }

    if ($script:slot -eq 5) {
        Release-Active "Completed all six scheduled slots by $((Get-Date).ToString('h:mm tt')) PT. See %LOCALAPPDATA%\MegaZword\FreeToolsContinuation\$jobId for per-slot logs and status."
    } else {
        Update-Active "Slot $($script:slot + 1)/6 passed. Next slot is scheduled at $($slotStart.AddHours(1).ToString('h:mm tt')) PT; hard stop 11:00 AM."
    }
    $commitResult = Check-PathsAndCommit $script:slot
    $nextDetail = if ($script:slot -eq 5) { 'Final morning slot complete; no further run is scheduled.' } else { "Next scheduled slot is $($slotStart.AddHours(1).ToString('h:mm tt')) PT." }
    Save-State 'completed' "$($labels[$script:slot]) $commitResult $nextDetail" $script:slot $result.ExitCode
} catch {
    $message = $_.Exception.Message
    if (Test-Path -LiteralPath $stopPath) {
        Save-State 'stopped' $message $script:slot 1
        try { Publish-Failure "Phil stopped the run. $message" } catch { }
        exit 0
    }
    Save-State 'blocked' $message $script:slot 1
    try { Publish-Failure $message } catch { }
    exit 1
}
