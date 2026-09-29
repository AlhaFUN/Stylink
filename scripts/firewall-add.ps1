$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell session.'
}

Get-NetFirewallRule -DisplayName 'Galaxy S23 Drawing Tablet' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    -DisplayName 'Galaxy S23 Drawing Tablet' `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8765 `
    -RemoteAddress LocalSubnet `
    -Profile Private

Write-Host 'Allowed TCP/8765 from the local subnet on the Private profile.'
