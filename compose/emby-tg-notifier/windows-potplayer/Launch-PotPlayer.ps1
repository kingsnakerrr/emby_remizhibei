param(
    [Parameter(Mandatory = $true)][string]$Link,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
try {
    if ($Link -cnotmatch '^hdz-potplayer://play/([A-Za-z0-9_-]{1,24000})/?$') {
        throw 'Invalid playback link.'
    }
    $encoded = $Matches[1].Replace('-', '+').Replace('_', '/')
    $encoded = $encoded.PadRight($encoded.Length + ((4 - $encoded.Length % 4) % 4), '=')
    $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $url = $utf8.GetString([Convert]::FromBase64String($encoded))
    $uri = $null
    if ($url -match '[\x00-\x20"\\]' -or
        -not [Uri]::TryCreate($url, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -notin @('http', 'https') -or -not $uri.Host -or $uri.UserInfo) {
        throw 'Only HTTP(S) video URLs are allowed.'
    }
    if ($ValidateOnly) { return $url }
    $exe = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'player-path.txt') -Raw).Trim()
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf) -or
        [IO.Path]::GetFileName($exe) -notin @('PotPlayerMini64.exe', 'PotPlayerMini.exe', 'PotPlayerMiniARM64.exe')) {
        throw 'PotPlayer was not found. Run Install.cmd again.'
    }
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $exe
    $start.UseShellExecute = $false
    # Quoted URL is the only argument; no cmd /c or PowerShell evaluation.
    $start.Arguments = '"' + $url + '"'
    [System.Diagnostics.Process]::Start($start) | Out-Null
} catch {
    if ($ValidateOnly) { throw }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show('Cannot open playback. Run Install.cmd again, then request a new Telegram link.', 'HDZ PotPlayer') | Out-Null
    exit 1
}
