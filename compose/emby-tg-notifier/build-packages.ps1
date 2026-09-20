$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root=$PSScriptRoot
$download=Join-Path $root 'app\downloads\potplayer-browser-launcher.zip'
if(Test-Path -LiteralPath $download) { Remove-Item -LiteralPath $download }
$archive=[IO.Compression.ZipFile]::Open($download,[IO.Compression.ZipArchiveMode]::Create)
try {
    foreach($method in @(1,2)) {
        $folder=if($method -eq 1) { '方法1.浏览器打开不常驻' } else { '方法2.安装后台常驻软件' }
        foreach($file in Get-ChildItem -LiteralPath (Join-Path $root 'windows-sync') -File) {
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$file.FullName,($folder+'/'+$file.Name),[IO.Compression.CompressionLevel]::Optimal)|Out-Null
        }
        foreach($file in Get-ChildItem -LiteralPath (Join-Path $root ('method'+$method)) -File) {
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$file.FullName,($folder+'/'+$file.Name),[IO.Compression.CompressionLevel]::Optimal)|Out-Null
        }
    }
} finally { $archive.Dispose() }
$out=[IO.Path]::GetFullPath((Join-Path $root '..\..\outputs'))
Copy-Item -LiteralPath $download -Destination (Join-Path $out 'JAV频道点播-v15.7.zip') -Force
$serverZip=Join-Path $out 'emby-tg-notifier-multi-v15.8-console.zip'
if(Test-Path -LiteralPath $serverZip) { Remove-Item -LiteralPath $serverZip }
$archive=[IO.Compression.ZipFile]::Open($serverZip,[IO.Compression.ZipArchiveMode]::Create)
try {
    $files=@('README.md','CONSOLE-v15.8.md','requirements.txt','Dockerfile','docker-compose.yml','build-packages.ps1','build-console-mark.py','build-console-icons.cjs') | ForEach-Object { Get-Item -LiteralPath (Join-Path $root $_) }
    foreach($dir in @('app','tests','windows-sync','method1','method2')) {
        $files+=Get-ChildItem -LiteralPath (Join-Path $root $dir) -File -Recurse | Where-Object { $_.FullName -notmatch '__pycache__|\.pyc$' }
    }
    foreach($file in $files) {
        $name=$file.FullName.Substring($root.Length+1).Replace('\','/')
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$file.FullName,$name,[IO.Compression.CompressionLevel]::Optimal)|Out-Null
    }
} finally { $archive.Dispose() }
Get-Item -LiteralPath $serverZip,$download
