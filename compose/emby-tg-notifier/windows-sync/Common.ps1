$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$script:AppName = -join ([char[]](74,65,86,39057,36947,28857,25773))
$script:AppRoot = Join-Path $env:LOCALAPPDATA 'JAV-Channel-Player'
$script:PsExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Read-Settings {
    $path = Join-Path $script:AppRoot 'settings.xml'
    if (Test-Path -LiteralPath $path) { return Import-Clixml -LiteralPath $path }
    return @{ Mode='Resident'; PlayerPath=''; Origin=''; Credential=$null }
}
function Save-Settings($Settings) {
    $Settings | Export-Clixml -LiteralPath (Join-Path $script:AppRoot 'settings.xml') -Encoding UTF8
}
function Get-DeviceToken($Settings) {
    if ($Settings.Credential) { return $Settings.Credential.GetNetworkCredential().Password }
    return ''
}
function Test-HttpUrl([string]$Url) {
    $uri = $null
    if ($Url -match '[\x00-\x20"\\]' -or -not [Uri]::TryCreate($Url,[UriKind]::Absolute,[ref]$uri) -or
        $uri.Scheme -notin @('http','https') -or -not $uri.Host -or $uri.UserInfo -or $uri.Fragment) {
        throw 'Invalid HTTP(S) URL.'
    }
    return $uri
}
function Decode-LaunchLink([string]$Link) {
    if ($Link -cnotmatch '^hdz-potplayer-sync://play/([A-Za-z0-9_-]{1,12000})/?$') { throw 'Invalid launch link.' }
    $text=$Matches[1].Replace('-','+').Replace('_','/')
    $text=$text.PadRight($text.Length+((4-$text.Length%4)%4),'=')
    $utf8=New-Object Text.UTF8Encoding($false,$true)
    $url=$utf8.GetString([Convert]::FromBase64String($text))
    $uri=Test-HttpUrl $url
    if ($uri.AbsolutePath -cnotmatch '/potplayer/claim/[A-Za-z0-9_-]{40,60}$' -or $uri.Query) { throw 'Invalid claim endpoint.' }
    return $url
}
function Endpoint-Base([string]$Url, [string]$Kind) {
    $null=Test-HttpUrl $Url
    $suffix='/potplayer/'+$Kind+'/'
    $index=$Url.LastIndexOf($suffix,[StringComparison]::Ordinal)
    if ($index -lt 0) { throw 'Invalid server endpoint.' }
    return $Url.Substring(0,$index)
}
function Invoke-Api([string]$Url,[string]$Token='', $Body=@{}) {
    $null=Test-HttpUrl $Url
    $headers=@{}
    if ($Token) { $headers.Authorization='Bearer '+$Token }
    # Never follow an authenticated redirect to an unrelated endpoint.
    Invoke-RestMethod -Uri $Url -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes(($Body|ConvertTo-Json -Compress))) -TimeoutSec 12 -MaximumRedirection 0
}
function Write-State([string]$State) {
    ('{0:u} {1}' -f [DateTime]::UtcNow,$State) | Set-Content -LiteralPath (Join-Path $script:AppRoot 'status.txt') -Encoding UTF8
}
function Show-Notice([string]$Text) {
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show($Text,$script:AppName) | Out-Null
}
function Assert-Player([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or
        [IO.Path]::GetFileName($Path) -notin @('PotPlayerMini64.exe','PotPlayerMini.exe','PotPlayerMiniARM64.exe')) {
        throw 'PotPlayer not found. Re-run Install.cmd and select the player executable.'
    }
}
function Start-Resident {
    Remove-Item -LiteralPath (Join-Path $script:AppRoot 'stop.request') -ErrorAction SilentlyContinue
    $launcher=Join-Path $script:AppRoot 'Launcher.vbs'
    $wscript=Join-Path $env:SystemRoot 'System32\wscript.exe'
    Start-Process -FilePath $wscript -ArgumentList ('//B //NoLogo "'+$launcher+'"') -WindowStyle Hidden | Out-Null
}
function Stop-Resident {
    New-Item -ItemType File -Path (Join-Path $script:AppRoot 'stop.request') -Force | Out-Null
    $mutex=New-Object Threading.Mutex($false,'Local\JAVChannelResident')
    try {
        $acquired=$false
        try { $acquired=$mutex.WaitOne(25000) } catch [Threading.AbandonedMutexException] { $acquired=$true }
        if (-not $acquired) { throw 'Close PotPlayer and wait for sync before updating or uninstalling.' }
        $mutex.ReleaseMutex()
    } finally { $mutex.Dispose() }
}

function Run-Playback([string]$ClaimUrl,[string]$DeviceToken='') {
    $settings=Read-Settings
    Assert-Player $settings.PlayerPath
    $mutex=New-Object Threading.Mutex($false,'Local\JAVChannelPlayback')
    $locked=$false
    try {
        try { $locked=$mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked=$true }
        if (-not $locked) { throw 'A channel playback is already active. Close it first.' }
        $base=Endpoint-Base $ClaimUrl 'claim'
        if ($settings.Origin -cne $base) { throw 'Server does not match this installation. Re-run installation or approve the browser server.' }
        $grant=Invoke-Api $ClaimUrl $DeviceToken
        $null=Test-HttpUrl $grant.url
        if ($grant.token -cnotmatch '^[A-Za-z0-9_-]{40,60}$' -or $grant.title -cnotmatch '^HDZ-[A-Za-z0-9_-]{10}$') { throw 'Invalid playback grant.' }
        $resume=[double]$grant.resume
        if ([double]::IsNaN($resume) -or [double]::IsInfinity($resume) -or $resume -lt 0 -or $resume -gt 1209600) { throw 'Invalid resume point.' }
        if (-not ('JavPot' -as [type])) { Add-Type -Path (Join-Path $script:AppRoot 'Native.cs') }
        $start=New-Object Diagnostics.ProcessStartInfo
        $start.FileName=$settings.PlayerPath
        $start.UseShellExecute=$false
        $start.Arguments='"'+$grant.url+'" /new /seek='+$resume.ToString('0.###',[Globalization.CultureInfo]::InvariantCulture)+' /title="'+$grant.title+'"'
        $player=[Diagnostics.Process]::Start($start)
        $started=[DateTime]::UtcNow
        $lastValid=$null
        $lastSent=[DateTime]::MinValue
        $lastPosition=-1.0
        $sequence=0
        $failed=0
        $lastGoodTime=[DateTime]::UtcNow
        $finished=$false
        Write-State 'Player launched. Waiting for a valid position.'
        while (-not $player.HasExited) {
            if ('Windows.Forms.Application' -as [type]) { [Windows.Forms.Application]::DoEvents() }
            Start-Sleep -Milliseconds 500
            $sample=[JavPot]::Read($player.Id,$grant.title)
            if ($sample.Valid) {
                $pos=$sample.PositionMs/1000.0
                $duration=$sample.DurationMs/1000.0
                # Allow the initial seek to settle; never overwrite a resume point with startup zero.
                if (-not $lastValid -and ($pos -le 0 -or ($resume -gt 5 -and $pos -lt $resume-3 -and ([DateTime]::UtcNow-$started).TotalSeconds -lt 15))) { continue }
                $lastValid=@{position=$pos; duration=$duration}
                $lastGoodTime=[DateTime]::UtcNow
                $seconds=([DateTime]::UtcNow-$lastSent).TotalSeconds
                if ($seconds -ge 10 -or ($lastPosition -ge 0 -and [Math]::Abs($pos-$lastPosition) -gt 15 -and $seconds -ge 2)) {
                    $sequence++
                    $body=@{event='progress';seq=$sequence;position=$pos;duration=$duration}
                    try {
                        $null=Invoke-Api ($base+'/potplayer/report') $grant.token $body
                        $lastSent=[DateTime]::UtcNow
                        $lastPosition=$pos
                        $failed=0
                        Write-State ('Emby progress saved: {0:0.0}s / {1:0.0}s' -f $pos,$duration)
                    } catch {
                        $failed++
                        $lastSent=[DateTime]::UtcNow
                        Write-State 'Progress upload failed; retrying. Previous saved Emby position is retained.'
                        if ($failed -ge 6) { break }
                    }
                }
            } elseif ($lastValid -and ([DateTime]::UtcNow-$lastGoodTime).TotalSeconds -ge 3) {
                # Stop syncing if the tracked media closes/changes; never attach to another video.
                break
            } elseif (-not $lastValid -and ([DateTime]::UtcNow-$started).TotalSeconds -ge 60) {
                Write-State 'No valid PotPlayer position. Playback was not recorded.'
                Show-Notice 'Could not read PotPlayer progress. No fake playback record was created. Check status.txt or try a current PotPlayer version.'
                break
            }
            if (([DateTime]::UtcNow-$started).TotalHours -ge 23) { break }
        }
        if ($lastValid) {
            $body=@{event='stop';seq=($sequence+1);position=$lastValid.position;duration=$lastValid.duration}
            for ($try=0;$try -lt 3;$try++) {
                try {
                    $null=Invoke-Api ($base+'/potplayer/report') $grant.token $body
                    Write-State ('Playback ended. Emby saved at {0:0.0}s.' -f $lastValid.position)
                    $finished=$true
                    break
                } catch { Start-Sleep -Seconds 2 }
            }
            if (-not $finished) {
                Write-State 'Final sync failed. Emby retains the last successful periodic update.'
                Show-Notice 'Final Emby sync failed. The last successfully uploaded position is retained.'
            }
        }
    } finally {
        if ($locked) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
