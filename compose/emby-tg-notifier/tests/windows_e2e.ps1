param([string]$Origin,[string]$TestRoot,[string]$PlayerPath,[string]$Mode='Browser')
$ErrorActionPreference='Stop'
$source=Join-Path (Split-Path $PSScriptRoot -Parent) 'windows-sync'
. (Join-Path $source 'Common.ps1')
$env:LOCALAPPDATA=$TestRoot
$script:AppRoot=Join-Path $TestRoot 'JAV-Channel-Player'
New-Item -ItemType Directory -Path $script:AppRoot | Out-Null
foreach($file in Get-ChildItem -LiteralPath $source -File) { Copy-Item -LiteralPath $file.FullName -Destination $script:AppRoot }
$settings=@{Mode=$Mode;Origin=$Origin;PlayerPath=$PlayerPath;Credential=$null}
if($Mode -eq 'Resident') { $settings.Credential=New-Object Management.Automation.PSCredential('test',(ConvertTo-SecureString ('d'*43) -AsPlainText -Force)) }
Save-Settings $settings
function Show-Notice([string]$Text) { throw $Text }
$before=@(Get-Process PotPlayerMini64 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
try {
    if($Mode -eq 'Resident') { & (Join-Path $script:AppRoot 'Resident.ps1') }
    else { Run-Playback ($Origin+'/potplayer/claim/'+('t'*43)) }
    Write-Output 'WINDOWS E2E PASS'
} finally {
    foreach($process in Get-Process PotPlayerMini64 -ErrorAction SilentlyContinue) {
        if($process.Id -notin $before -and $process.MainWindowTitle.Contains('HDZ-1234567890')) {
            $null=$process.CloseMainWindow()
            if(-not $process.WaitForExit(5000)) { $process.Kill() }
        }
    }
}
