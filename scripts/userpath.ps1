# Add a folder to the current user's PATH without damaging it.
# Dot-sourced by install.ps1; tests point -KeyPath at a throwaway key.
#
# Why not [Environment]::GetEnvironmentVariable('Path','User')? It returns the
# value with %VARS% already expanded, so writing it back silently turns every
# "%USERPROFILE%\..." entry into a fixed path forever. This reads the raw
# registry value and writes it back as REG_EXPAND_SZ.

function Add-UserPath {
    param(
        [Parameter(Mandatory)][string]$Directory,
        [string]$KeyPath = 'Environment',
        [switch]$NoBroadcast
    )
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($KeyPath)
    try {
        $raw = [string]$key.GetValue('Path', '',
            [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $parts = @($raw -split ';' | Where-Object { $_.Trim() })
        $want = $Directory.TrimEnd('\')
        $already = $parts | Where-Object {
            $_.TrimEnd('\') -ieq $want -or
            [Environment]::ExpandEnvironmentVariables($_).TrimEnd('\') -ieq $want
        }
        if (-not $already) {
            # Keep every existing entry exactly as written (duplicates included);
            # only empty entries from stray semicolons are dropped.
            $key.SetValue('Path', (($parts + $Directory) -join ';'),
                [Microsoft.Win32.RegistryValueKind]::ExpandString)
            if (-not $NoBroadcast) {
                # A raw registry write doesn't tell Windows the environment
                # changed; setting and clearing a dummy variable does, so new
                # terminals pick up the PATH without a sign-out.
                [Environment]::SetEnvironmentVariable('MEGAZWORD_PATH_REFRESH', '1', 'User')
                [Environment]::SetEnvironmentVariable('MEGAZWORD_PATH_REFRESH', $null, 'User')
            }
        }
    } finally {
        $key.Close()
    }
    if (-not (($env:Path -split ';') | Where-Object { $_.TrimEnd('\') -ieq $Directory.TrimEnd('\') })) {
        $env:Path = ($env:Path.TrimEnd(';') + ";$Directory")
    }
}
