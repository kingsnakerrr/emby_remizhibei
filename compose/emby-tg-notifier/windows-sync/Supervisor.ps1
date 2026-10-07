. (Join-Path $PSScriptRoot 'Common.ps1')
$mutex=New-Object Threading.Mutex($false,'Local\JAVChannelSupervisor')
$locked=$false
try {
    try { $locked=$mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked=$true }
    if(-not $locked) { exit }
    while(-not (Test-Path -LiteralPath (Join-Path $script:AppRoot 'stop.request'))) {
        $resident=Start-Process -FilePath $script:PsExe `
            -ArgumentList ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+(Join-Path $script:AppRoot 'Resident.ps1')+'"') `
            -WindowStyle Hidden -PassThru
        while(-not $resident.HasExited) {
            if(Test-Path -LiteralPath (Join-Path $script:AppRoot 'stop.request')) {
                Stop-Process -Id $resident.Id -Force -ErrorAction SilentlyContinue
                $resident.WaitForExit()
                break
            }
            Start-Sleep -Milliseconds 500
            $resident.Refresh()
        }
        if(Test-Path -LiteralPath (Join-Path $script:AppRoot 'stop.request')) { break }
        Write-State 'Desktop receiver stopped unexpectedly; restarting automatically.'
        Start-Sleep -Seconds 3
    }
} finally {
    if($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
