param([string]$PlayerPath='C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Add-Type -Path (Join-Path $root 'windows-sync\Native.cs')
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class JavTestControl {
    [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);
}
'@
$directory=Join-Path ([IO.Path]::GetTempPath()) ('jav-player-test-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directory | Out-Null
$file=Join-Path $directory 'silent-test.wav'
$rate=8000
$length=$rate*2*45
$writer=New-Object IO.BinaryWriter([IO.File]::Create($file))
try {
    $writer.Write([Text.Encoding]::ASCII.GetBytes('RIFF'))
    $writer.Write([int](36+$length))
    $writer.Write([Text.Encoding]::ASCII.GetBytes('WAVEfmt '))
    $writer.Write([int]16); $writer.Write([int16]1); $writer.Write([int16]1)
    $writer.Write([int]$rate); $writer.Write([int]($rate*2))
    $writer.Write([int16]2); $writer.Write([int16]16)
    $writer.Write([Text.Encoding]::ASCII.GetBytes('data')); $writer.Write([int]$length)
    $writer.Write((New-Object byte[] $length))
} finally { $writer.Dispose() }
$player=$null
try {
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=$PlayerPath
    $start.Arguments='"'+$file+'" /new /seek=5 /title="HDZ-test123456"'
    $start.UseShellExecute=$false
    $player=[Diagnostics.Process]::Start($start)
    $sample=$null
    for($i=0;$i -lt 40;$i++) {
        Start-Sleep -Milliseconds 500
        $sample=[JavPot]::Read($player.Id,'HDZ-test123456')
        if($sample.Valid -and $sample.PositionMs -ge 5000) { break }
    }
    if(-not $sample.Valid -or $sample.PositionMs -lt 5000 -or [Math]::Abs($sample.DurationMs-45000) -gt 1000) { throw 'Native PotPlayer sample/seek failed.' }
    $first=$sample.PositionMs
    Start-Sleep -Seconds 2
    $later=[JavPot]::Read($player.Id,'HDZ-test123456')
    if(-not $later.Valid -or $later.PositionMs -le $first) { throw 'Playback clock did not advance.' }
    if(([JavPot]::Read($player.Id,'not-this-media')).Valid) { throw 'Wrong-media marker was accepted.' }
    $player.Refresh()
    $window=$player.MainWindowHandle
    $null=[JavTestControl]::SendMessageW($window,0x400,[IntPtr]0x5007,[IntPtr]1)
    Start-Sleep -Milliseconds 300
    $paused=[JavPot]::Read($player.Id,'HDZ-test123456')
    Start-Sleep -Seconds 1
    $still=[JavPot]::Read($player.Id,'HDZ-test123456')
    if($still.State -ne 1 -or [Math]::Abs($paused.PositionMs-$still.PositionMs) -gt 100) { throw 'Pause detection failed.' }
    $null=[JavTestControl]::SendMessageW($window,0x400,[IntPtr]0x5005,[IntPtr]2000)
    $null=[JavTestControl]::SendMessageW($window,0x400,[IntPtr]0x5007,[IntPtr]2)
    Start-Sleep -Milliseconds 800
    $rewound=[JavPot]::Read($player.Id,'HDZ-test123456')
    if(-not $rewound.Valid -or $rewound.PositionMs -ge $still.PositionMs) { throw 'Seek/rewind detection failed.' }
    Write-Host ('REAL POTPLAYER PASS: seek={0}ms later={1}ms duration={2}ms' -f $first,$later.PositionMs,$later.DurationMs)
    Write-Host 'REAL POTPLAYER PASS: pause, unpause, rewind, wrong-media rejection.'
} finally {
    if($player -and -not $player.HasExited) {
        $null=$player.CloseMainWindow()
        if(-not $player.WaitForExit(5000)) { $player.Kill(); $player.WaitForExit() }
    }
    $resolved=(Resolve-Path -LiteralPath $directory).Path
    if($resolved -eq [IO.Path]::GetFullPath($directory) -and $resolved.StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $file; Remove-Item -LiteralPath $directory }
}
