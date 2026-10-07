param([string]$PlayerPath='', [switch]$RePair, [switch]$NoStart)
. (Join-Path $PSScriptRoot 'Common.ps1')
try {
    $check=New-Object Threading.Mutex($false,'Local\JAVChannelPlayback')
    try {
        $free=$false
        try { $free=$check.WaitOne(0) } catch [Threading.AbandonedMutexException] { $free=$true }
        if(-not $free) { throw 'Close channel playback before installing or updating.' }
        $check.ReleaseMutex()
    } finally { $check.Dispose() }
    New-Item -ItemType Directory -Path $script:AppRoot -Force | Out-Null
    $settings=Read-Settings
    if(-not $PlayerPath) { $PlayerPath=$settings.PlayerPath }
    if(-not $PlayerPath -or -not (Test-Path -LiteralPath $PlayerPath -PathType Leaf)) {
        $candidates=foreach($root in @($env:ProgramFiles,${env:ProgramFiles(x86)},$env:LOCALAPPDATA)) {
            if($root) { foreach($relative in @('DAUM\PotPlayer\PotPlayerMini64.exe','DAUM\PotPlayer\PotPlayerMini.exe','PotPlayer\PotPlayerMini64.exe')) { Join-Path $root $relative } }
        }
        $PlayerPath=$candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if(-not $PlayerPath) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog=New-Object Windows.Forms.OpenFileDialog
        $dialog.Title='Select PotPlayer executable'
        $dialog.Filter='PotPlayer|PotPlayerMini64.exe;PotPlayerMini.exe;PotPlayerMiniARM64.exe'
        if($dialog.ShowDialog() -ne 'OK') { throw 'Installation cancelled.' }
        $PlayerPath=$dialog.FileName
    }
    Assert-Player $PlayerPath
    $settings.PlayerPath=(Resolve-Path -LiteralPath $PlayerPath).Path
    if($RePair -or -not $settings.Credential) {
        Write-Host 'In your Telegram bot, send /pc (or /pc SERVER_ID).'
        $link=(Read-Host 'Paste the single-use pairing URL from the bot').Trim()
        $uri=Test-HttpUrl $link
        if($uri.AbsolutePath -cnotmatch '/potplayer/pair/[A-Za-z0-9_-]{32}$' -or $uri.Query) { throw 'Invalid pairing URL.' }
        $origin=Endpoint-Base $link 'pair'
        if($uri.Scheme -eq 'http') {
            Write-Warning 'HTTP does not encrypt pairing credentials or playback URLs. Prefer HTTPS.'
            if((Read-Host 'Type YES to continue using HTTP') -cne 'YES') { throw 'Pairing cancelled.' }
        }
        $paired=Invoke-Api $link
        if($paired.token -cnotmatch '^[A-Za-z0-9_-]{40,60}$') { throw 'Invalid pairing response.' }
        $settings.Origin=$origin
        $settings.Credential=New-Object Management.Automation.PSCredential('JAVChannelPlayer',(ConvertTo-SecureString $paired.token -AsPlainText -Force))
    }
    Stop-Resident
    # Give an already installed supervisor time to stop and release its single-instance mutex.
    Start-Sleep -Seconds 2
    $files=@('Common.ps1','Native.cs','Resident.ps1','Supervisor.ps1','Launcher.vbs','Install.ps1','Manage.ps1','Install.cmd','Uninstall.cmd','Start.cmd','Stop.cmd','RePair.cmd','VERSION.txt')
    foreach($name in $files) {
        $source=Join-Path $PSScriptRoot $name
        $dest=Join-Path $script:AppRoot $name
        if([IO.Path]::GetFullPath($source) -ine [IO.Path]::GetFullPath($dest)) { Copy-Item -LiteralPath $source -Destination $dest -Force }
    }
    $settings.Mode='Resident'
    Save-Settings $settings
    # Remove the retired browser protocol. PotPlayer is now launched only by the paired desktop receiver.
    $key='HKCU:\Software\Classes\hdz-potplayer-sync'
    if(Test-Path -LiteralPath $key) { Remove-Item -LiteralPath $key -Recurse -Force }
    $run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $launcher='"'+(Join-Path $env:SystemRoot 'System32\wscript.exe')+'" //B //NoLogo "'+(Join-Path $script:AppRoot 'Launcher.vbs')+'"'
    New-Item -Path $run -Force | Out-Null
    New-ItemProperty -Path $run -Name 'JAVChannelPlayer' -Value $launcher -PropertyType String -Force | Out-Null
    $uninstall='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\JAVChannelPlayer'
    New-Item -Path $uninstall -Force | Out-Null
    $properties=@{
        DisplayName=$script:AppName; DisplayVersion='15.9'; Publisher='JAV Channel Player';
        InstallLocation=$script:AppRoot;
        UninstallString=('"'+$script:PsExe+'" -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $script:AppRoot 'Manage.ps1')+'" -Action Uninstall')
    }
    foreach($entry in $properties.GetEnumerator()) { New-ItemProperty -Path $uninstall -Name $entry.Key -Value $entry.Value -PropertyType String -Force | Out-Null }
    $menu=Join-Path ([Environment]::GetFolderPath('Programs')) $script:AppName
    New-Item -ItemType Directory -Path $menu -Force | Out-Null
    $shell=New-Object -ComObject WScript.Shell
    foreach($action in @('Start','Stop','Uninstall')) {
        $shortcut=$shell.CreateShortcut((Join-Path $menu ($script:AppName+' - '+$action+'.lnk')))
        $shortcut.TargetPath=$script:PsExe
        $shortcut.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $script:AppRoot 'Manage.ps1')+'" -Action '+$action
        $shortcut.WindowStyle=7
        $shortcut.Save()
    }
    Write-State 'Version 15.9 installed/updated; direct desktop mode enabled.'
    if(-not $NoStart) { Start-Resident }
    Write-Host ($script:AppName+' 15.9 installed/updated. Existing pairing is preserved.')
    Write-Host 'Uninstall from Windows Settings > Apps, or run Uninstall.cmd.'
    Write-Host 'Close this window and request a NEW Telegram playback link.'
} catch {
    Write-Host ('Installation failed: '+$_.Exception.Message) -ForegroundColor Red
    exit 1
}
