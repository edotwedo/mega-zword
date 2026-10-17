# Auto-name new interactive Codex sessions; resumes and noninteractive commands pass through.
function global:codex {
    & 'C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe' 'C:\Users\mrmar\AppData\Local\MegaZword\CodexNames\launch.py' @args
    $global:LASTEXITCODE = $LASTEXITCODE
}
