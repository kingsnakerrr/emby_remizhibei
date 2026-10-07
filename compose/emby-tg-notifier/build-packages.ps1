$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root=$PSScriptRoot
$download=Join-Path $root 'app\downloads\potplayer-browser-launcher.zip'
if(Test-Path -LiteralPath $download) { Remove-Item -LiteralPath $download }
$archive=[IO.Compression.ZipFile]::Open($download,[IO.Compression.ZipArchiveMode]::Create)
try {
    foreach($file in Get-ChildItem -LiteralPath (Join-Path $root 'windows-sync') -File) {
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$file.FullName,$file.Name,[IO.Compression.CompressionLevel]::Optimal)|Out-Null
    }
} finally { $archive.Dispose() }
$out=[IO.Path]::GetFullPath((Join-Path $root '..\..\outputs'))
New-Item -ItemType Directory -Path $out -Force | Out-Null
Copy-Item -LiteralPath $download -Destination (Join-Path $out 'JAV频道点播-v15.9.zip') -Force
$serverZip=Join-Path $out 'emby-tg-notifier-multi-v15.8-console.zip'
if(Test-Path -LiteralPath $serverZip) { Remove-Item -LiteralPath $serverZip }
$archive=[IO.Compression.ZipFile]::Open($serverZip,[IO.Compression.ZipArchiveMode]::Create)
try {
    $files=@('README.md','CONSOLE-v15.8.md','requirements.txt','Dockerfile','docker-compose.yml','build-packages.ps1','build-console-mark.py','build-console-icons.cjs') | ForEach-Object { Get-Item -LiteralPath (Join-Path $root $_) }
    foreach($dir in @('app','tests','windows-sync')) {
        $files+=Get-ChildItem -LiteralPath (Join-Path $root $dir) -File -Recurse | Where-Object { $_.FullName -notmatch '__pycache__|\.pyc$' }
    }
    foreach($file in $files) {
        $name=$file.FullName.Substring($root.Length+1).Replace('\','/')
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$file.FullName,$name,[IO.Compression.CompressionLevel]::Optimal)|Out-Null
    }
} finally { $archive.Dispose() }
Get-Item -LiteralPath $serverZip,$download
