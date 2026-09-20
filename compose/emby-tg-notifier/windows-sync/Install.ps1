param([ValidateSet('Browser','Resident')][string]$Mode='Browser', [string]$PlayerPath='', [switch]$RePair, [switch]$NoStart)
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
    if($Mode -eq 'Resident' -and ($RePair -or -not $settings.Credential)) {
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
    if($Mode -eq 'Browser' -and $settings.Credential) {
        # Switching modes revokes desktop delivery, while preserving the media binding in Emby/TG.
        try { $null=Invoke-Api ($settings.Origin+'/potplayer/revoke') (Get-DeviceToken $settings) }
        catch { Write-Warning 'Could not revoke online. Send /pc_off to your Telegram bot as well.' }
        $settings.Credential=$null
    }
    Stop-Resident
    $files=@('Common.ps1','Native.cs','Bridge.ps1','Resident.ps1','Install.ps1','Manage.ps1','Install.cmd','Uninstall.cmd','Start.cmd','Stop.cmd','RePair.cmd','VERSION.txt')
    foreach($name in $files) {
        $source=Join-Path $PSScriptRoot $name
        $dest=Join-Path $script:AppRoot $name
        if([IO.Path]::GetFullPath($source) -ine [IO.Path]::GetFullPath($dest)) { Copy-Item -LiteralPath $source -Destination $dest -Force }
    }
    $settings.Mode=$Mode
    Save-Settings $settings
    $key='HKCU:\Software\Classes\hdz-potplayer-sync'
    New-Item -Path "$key\shell\open\command" -Force | Out-Null
    Set-Item -Path $key -Value ('URL:'+$script:AppName)
    New-ItemProperty -Path $key -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
    $bridge=Join-Path $script:AppRoot 'Bridge.ps1'
    Set-Item -Path "$key\shell\open\command" -Value ('"'+$script:PsExe+'" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$bridge+'" -Link "%1"')
    $run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $resident='"'+$script:PsExe+'" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+(Join-Path $script:AppRoot 'Resident.ps1')+'"'
    if($Mode -eq 'Resident') {
        New-Item -Path $run -Force | Out-Null
        New-ItemProperty -Path $run -Name 'JAVChannelPlayer' -Value $resident -PropertyType String -Force | Out-Null
    } else { Remove-ItemProperty -Path $run -Name 'JAVChannelPlayer' -ErrorAction SilentlyContinue }
    $uninstall='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\JAVChannelPlayer'
    New-Item -Path $uninstall -Force | Out-Null
    $properties=@{
        DisplayName=$script:AppName; DisplayVersion='15.7'; Publisher='JAV Channel Player';
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
    Write-State ('Version 15.7 installed/updated; mode='+$Mode)
    if($Mode -eq 'Resident' -and -not $NoStart) { Start-Resident }
    Write-Host ($script:AppName+' 15.7 installed/updated. Existing pairing is preserved on same-mode updates.')
    Write-Host 'Uninstall from Windows Settings > Apps, or run Uninstall.cmd.'
    Write-Host 'Close this window and request a NEW Telegram playback link.'
} catch {
    Write-Host ('Installation failed: '+$_.Exception.Message) -ForegroundColor Red
    exit 1
}
