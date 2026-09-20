$ErrorActionPreference = 'Stop'
# Remove only our protocol registration; leave files and other player associations.
$key = 'HKCU:\Software\Classes\hdz-potplayer'
if (Test-Path -LiteralPath $key) {
    Remove-Item -LiteralPath $key -Recurse -Force
}
Write-Host 'HDZ PotPlayer protocol removed. PotPlayer itself is unchanged.'
