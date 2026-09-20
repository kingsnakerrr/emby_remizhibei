$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
foreach($file in Get-ChildItem -LiteralPath (Join-Path $root 'windows-sync') -Filter '*.ps1') {
    $tokens=$null; $errors=$null
    [Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)|Out-Null
    if($errors.Count) { throw "Syntax errors: $errors" }
}
. (Join-Path $root 'windows-sync\Common.ps1')
function Encode-Link([string]$url) {
    'hdz-potplayer-sync://play/'+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($url)).TrimEnd('=').Replace('+','-').Replace('/','_')
}
foreach($base in @('https://notifier.invalid','http://127.0.0.1:8787','https://notifier.invalid/prefix')) {
    $url=$base+'/potplayer/claim/'+('a'*43)
    if((Decode-LaunchLink (Encode-Link $url)) -cne $url) { throw 'URL roundtrip failed.' }
    if((Endpoint-Base $url 'claim') -cne $base) { throw 'Server path prefix lost.' }
}
foreach($url in @('file:///C:/Windows/calc.exe','javascript:alert(1)','https://a.invalid/x" /evil',"https://a.invalid/x`r`n",'https://user:pass@a.invalid/x','https://a.invalid\x')) {
    $rejected=$false
    try { Test-HttpUrl $url | Out-Null } catch { $rejected=$true }
    if(-not $rejected) { throw 'Unsafe URL accepted.' }
}
foreach($link in @('hdz-potplayer-sync://play/a','hdz-potplayer-sync://play/!!!',(Encode-Link 'https://a.invalid/not-a-claim'),(Encode-Link ('https://a.invalid/potplayer/claim/'+('a'*43)+'?bad=1')))) {
    $rejected=$false
    try { Decode-LaunchLink $link | Out-Null } catch { $rejected=$true }
    if(-not $rejected) { throw 'Malformed claim link accepted.' }
}
Write-Output 'PASS: 13 URL/claim tests; all Windows scripts parse.'
