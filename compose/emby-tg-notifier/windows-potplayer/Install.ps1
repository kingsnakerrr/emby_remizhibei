param([string]$PlayerPath)
$ErrorActionPreference = 'Stop'
try {
    if (-not $PlayerPath) {
        $candidates = foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
            if ($root) {
                foreach ($relative in @('DAUM\PotPlayer\PotPlayerMini64.exe', 'DAUM\PotPlayer\PotPlayerMini.exe', 'PotPlayer\PotPlayerMini64.exe')) {
                    Join-Path $root $relative
                }
            }
        }
        $PlayerPath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if (-not $PlayerPath) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = 'Select PotPlayerMini64.exe or PotPlayerMini.exe'
        $dialog.Filter = 'PotPlayer|PotPlayerMini64.exe;PotPlayerMini.exe;PotPlayerMiniARM64.exe'
        if ($dialog.ShowDialog() -ne 'OK') { throw 'Installation cancelled.' }
        $PlayerPath = $dialog.FileName
    }
    $PlayerPath = (Resolve-Path -LiteralPath $PlayerPath).Path
    if ([IO.Path]::GetFileName($PlayerPath) -notin @('PotPlayerMini64.exe', 'PotPlayerMini.exe', 'PotPlayerMiniARM64.exe')) {
        throw 'Select a PotPlayer executable.'
    }
    $target = Join-Path $env:LOCALAPPDATA 'HDZ-PotPlayer'
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Launch-PotPlayer.ps1') -Destination $target -Force
    Set-Content -LiteralPath (Join-Path $target 'player-path.txt') -Value $PlayerPath -Encoding UTF8
    $key = 'HKCU:\Software\Classes\hdz-potplayer'
    New-Item -Path "$key\shell\open\command" -Force | Out-Null
    Set-Item -Path $key -Value 'URL:HDZ PotPlayer'
    New-ItemProperty -Path $key -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
    $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $script = Join-Path $target 'Launch-PotPlayer.ps1'
    $command = '"{0}" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}" -Link "%1"' -f $powershell, $script
    Set-Item -Path "$key\shell\open\command" -Value $command
    Write-Host 'Installed for this Windows user. Return to Telegram and request a new PotPlayer link.'
    Write-Host 'No administrator access required. Existing potplayer:// associations are unchanged.'
} catch {
    Write-Error $_
    exit 1
}
