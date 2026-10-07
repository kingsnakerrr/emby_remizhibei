$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
foreach($file in Get-ChildItem -LiteralPath (Join-Path $root 'windows-sync') -Filter '*.ps1') {
    $tokens=$null; $errors=$null
    [Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)|Out-Null
    if($errors.Count) { throw "Syntax errors: $errors" }
}
. (Join-Path $root 'windows-sync\Common.ps1')
foreach($url in @('file:///C:/Windows/calc.exe','javascript:alert(1)','https://a.invalid/x" /evil',"https://a.invalid/x`r`n",'https://user:pass@a.invalid/x','https://a.invalid\x')) {
    $rejected=$false
    try { Test-HttpUrl $url | Out-Null } catch { $rejected=$true }
    if(-not $rejected) { throw 'Unsafe URL accepted.' }
}
Write-Output 'PASS: unsafe URL tests; all direct-play Windows scripts parse.'
