param([ValidateSet('Start','Stop','Uninstall')][string]$Action='Start', [switch]$Quiet)
. (Join-Path $PSScriptRoot 'Common.ps1')
try {
    if($Action -eq 'Start') {
        $settings=Read-Settings
        if(-not $settings.Credential) { Show-Notice 'This computer is not paired. Run Install.cmd and use /pc in Telegram.'; exit 1 }
        Start-Resident
        exit
    }
    $check=New-Object Threading.Mutex($false,'Local\JAVChannelPlayback')
    try {
        $free=$false
        try { $free=$check.WaitOne(0) } catch [Threading.AbandonedMutexException] { $free=$true }
        if(-not $free) { throw 'Close the channel playback and allow progress sync to finish first.' }
        $check.ReleaseMutex()
    } finally { $check.Dispose() }
    Stop-Resident
    if($Action -eq 'Stop') { Write-State 'Resident receiver stopped. Logon startup remains enabled; use Uninstall to remove it.'; exit }
    $settings=Read-Settings
    if($settings.Credential) {
        try { $null=Invoke-Api ($settings.Origin+'/potplayer/revoke') (Get-DeviceToken $settings) }
        catch { Show-Notice 'Online revocation failed. Send /pc_off to your Telegram bot to revoke this computer.' }
    }
    Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'JAVChannelPlayer' -ErrorAction SilentlyContinue
    foreach($key in @('HKCU:\Software\Classes\hdz-potplayer-sync','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\JAVChannelPlayer')) {
        if(Test-Path -LiteralPath $key) { Remove-Item -LiteralPath $key -Recurse -Force }
    }
    # Delete only the verified per-user installation directory and our own Start-menu folder.
    $expected=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'JAV-Channel-Player'))
    $resolved=(Resolve-Path -LiteralPath $script:AppRoot).Path
    $item=Get-Item -LiteralPath $resolved
    if($resolved -ine $expected -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe uninstall directory; refusing deletion.' }
    $programs=[Environment]::GetFolderPath('Programs')
    $menu=Join-Path $programs $script:AppName
    if(Test-Path -LiteralPath $menu) {
        $menuItem=Get-Item -LiteralPath $menu
        if(($menuItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $menuItem.FullName -ine [IO.Path]::GetFullPath((Join-Path $programs $script:AppName))) { throw 'Unsafe shortcut directory.' }
        foreach($actionName in @('Start','Stop','Uninstall')) { Remove-Item -LiteralPath (Join-Path $menu ($script:AppName+' - '+$actionName+'.lnk')) -ErrorAction SilentlyContinue }
        if(-not (Get-ChildItem -LiteralPath $menu -Force)) { Remove-Item -LiteralPath $menu }
    }
    foreach($child in Get-ChildItem -LiteralPath $resolved -Recurse -Force) {
        if($child.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point found; refusing recursive deletion.' }
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
    if(-not $Quiet) { Show-Notice 'Uninstalled. PotPlayer, Emby server data, Telegram binding, and playback records were not deleted.' }
} catch { if($Quiet) { throw } else { Show-Notice $_.Exception.Message; exit 1 } }
