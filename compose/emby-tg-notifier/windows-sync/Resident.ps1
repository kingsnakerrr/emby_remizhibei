. (Join-Path $PSScriptRoot 'Common.ps1')
$mutex=New-Object Threading.Mutex($false,'Local\JAVChannelResident')
$locked=$false
$icon=$null
try {
    try { $locked=$mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked=$true }
    if (-not $locked) { exit }
    $settings=Read-Settings
    $token=Get-DeviceToken $settings
    if ($settings.Mode -ne 'Resident' -or -not $token) { throw 'Not paired.' }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $icon=New-Object Windows.Forms.NotifyIcon
    $icon.Icon=[Drawing.SystemIcons]::Application
    $icon.Text=$script:AppName
    $menu=New-Object Windows.Forms.ContextMenu
    $status=$menu.MenuItems.Add('Status')
    $status.Add_Click({ if(Test-Path -LiteralPath (Join-Path $script:AppRoot 'status.txt')) { Show-Notice (Get-Content -LiteralPath (Join-Path $script:AppRoot 'status.txt') -Raw) } })
    $quit=$menu.MenuItems.Add('Exit')
    $quit.Add_Click({ New-Item -ItemType File -Path (Join-Path $script:AppRoot 'stop.request') -Force | Out-Null })
    $icon.ContextMenu=$menu
    $icon.Visible=$true
    Write-State 'Desktop receiver online. Click PotPlayer in Telegram.'
    while (-not (Test-Path -LiteralPath (Join-Path $script:AppRoot 'stop.request'))) {
        [Windows.Forms.Application]::DoEvents()
        try {
            $job=Invoke-Api ($settings.Origin+'/potplayer/poll') $token
            if ($job.ticket) {
                if ($job.ticket -cnotmatch '^[A-Za-z0-9_-]{40,60}$') { throw 'Invalid ticket.' }
                Run-Playback ($settings.Origin+'/potplayer/claim/'+$job.ticket) $token
            }
        } catch {
            if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -in @(401,403)) {
                Write-State 'Pairing is currently rejected. Re-run Install.cmd to pair again; receiver remains available.'
                for($i=0;$i -lt 50;$i++) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 200 }
                continue
            }
            Write-State 'Receiver could not complete request. Check connectivity or request a new playback.'
        }
        for($i=0;$i -lt 10;$i++) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 200 }
    }
} catch { Write-State 'Receiver failed to start. Re-run Install.cmd.' }
finally {
    if($icon) { $icon.Visible=$false; $icon.Dispose() }
    if($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
