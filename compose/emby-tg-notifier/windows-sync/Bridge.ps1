param([Parameter(Mandatory=$true)][string]$Link)
. (Join-Path $PSScriptRoot 'Common.ps1')
try {
    $url=Decode-LaunchLink $Link
    $origin=Endpoint-Base $url 'claim'
    $settings=Read-Settings
    if ($settings.Origin -cne $origin) {
        Add-Type -AssemblyName System.Windows.Forms
        $warning='Allow this notification server to start PotPlayer and save your Emby progress?'+[Environment]::NewLine+$origin
        if ($origin.StartsWith('http://')) { $warning += [Environment]::NewLine+'WARNING: HTTP is not encrypted. Use HTTPS where possible.' }
        $answer=[Windows.Forms.MessageBox]::Show($warning,$script:AppName,[Windows.Forms.MessageBoxButtons]::YesNo,[Windows.Forms.MessageBoxIcon]::Warning)
        if ($answer -ne 'Yes') { exit 1 }
        if ($settings.Credential) { throw 'This installation is paired to a different server. Unpair before switching.' }
        $settings.Origin=$origin
        Save-Settings $settings
    }
    Run-Playback $url
} catch {
    Write-State 'Playback launch failed. Request a new Telegram link; check installation, binding, and server availability.'
    Show-Notice 'Playback could not start or synchronize. Request a new Telegram link. Check PotPlayer path, Emby binding, and server availability.'
    exit 1
}
