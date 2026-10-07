$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$name=-join([char[]](74,65,86,39057,36947,28857,25773))
$menu=Join-Path ([Environment]::GetFolderPath('Programs')) $name
if(Test-Path -LiteralPath $menu) { throw 'Existing real installation found; refusing lifecycle test.' }
$oldLocal=$env:LOCALAPPDATA
$sandbox=Join-Path ([IO.Path]::GetTempPath()) ('jav-install-test-'+[Guid]::NewGuid().ToString('N'))
$registry='HKEY_CURRENT_USER\Software\JAVTest'+[Guid]::NewGuid().ToString('N')
New-Item -Path ('Registry::'+$registry) -Force | Out-Null
New-Item -ItemType Directory -Path $sandbox | Out-Null
try {
    Remove-PSDrive HKCU
    New-PSDrive -Name HKCU -PSProvider Registry -Root $registry | Out-Null
    $env:LOCALAPPDATA=$sandbox
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $unpack=Join-Path $sandbox 'package'
    [IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $root 'app\downloads\potplayer-browser-launcher.zip'),$unpack)
    $installed=Join-Path $sandbox 'JAV-Channel-Player'
    New-Item -ItemType Directory -Path $installed -Force | Out-Null
    $credential=New-Object Management.Automation.PSCredential('test',(ConvertTo-SecureString ('secret-fixture'*4) -AsPlainText -Force))
    @{Mode='Resident';PlayerPath='C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe';Origin='https://notifier.invalid';Credential=$credential}|Export-Clixml -LiteralPath (Join-Path $installed 'settings.xml')
    & (Join-Path $unpack 'Install.ps1') -PlayerPath 'C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe' -NoStart
    if($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'Direct installation failed.' }
    if(-not (Test-Path -LiteralPath (Join-Path $installed 'Uninstall.cmd'))) { throw 'Uninstaller missing.' }
    $display=(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\JAVChannelPlayer').DisplayName
    if($display -cne $name) { throw 'Wrong product name.' }
    $before=Import-Clixml -LiteralPath (Join-Path $installed 'settings.xml')
    & (Join-Path $unpack 'Install.ps1') -NoStart
    $after=Import-Clixml -LiteralPath (Join-Path $installed 'settings.xml')
    if($after.Credential.GetNetworkCredential().Password -cne $before.Credential.GetNetworkCredential().Password) { throw 'Update lost pairing.' }
    if((Get-Content -LiteralPath (Join-Path $installed 'settings.xml') -Raw).Contains('secret-fixture')) { throw 'Pairing saved in plaintext.' }
    $startup=(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name JAVChannelPlayer).JAVChannelPlayer
    if($startup -notmatch 'wscript\.exe' -or $startup -notmatch 'Launcher\.vbs') { throw 'Hidden supervisor startup missing.' }
    if(Test-Path 'HKCU:\Software\Classes\hdz-potplayer-sync') { throw 'Retired browser protocol remains.' }
    foreach($file in @('Supervisor.ps1','Launcher.vbs')) { if(-not (Test-Path -LiteralPath (Join-Path $installed $file))) { throw "$file missing." } }
    & (Join-Path $installed 'Manage.ps1') -Action Uninstall -Quiet
    if(Test-Path -LiteralPath $installed) { throw 'Uninstall left program files.' }
    if(Test-Path 'HKCU:\Software\Classes\hdz-potplayer-sync') { throw 'Uninstall left protocol.' }
    if(Test-Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\JAVChannelPlayer') { throw 'Uninstall registration remains.' }
    if(Test-Path -LiteralPath $menu) { throw 'Start menu folder remains.' }
    Write-Output 'PASS: direct install, DPAPI, repeat update preserves pairing, hidden watchdog startup, uninstall.'
} finally {
    $env:LOCALAPPDATA=$oldLocal
    Remove-PSDrive HKCU -ErrorAction SilentlyContinue
    New-PSDrive -Name HKCU -PSProvider Registry -Root HKEY_CURRENT_USER | Out-Null
    Remove-Item -LiteralPath ('Registry::'+$registry) -Recurse -Force
    $resolved=(Resolve-Path -LiteralPath $sandbox).Path
    if($resolved -eq [IO.Path]::GetFullPath($sandbox) -and $resolved.StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
