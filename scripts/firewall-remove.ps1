$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell session.'
}

Get-NetFirewallRule -DisplayName 'Galaxy S23 Drawing Tablet' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

Write-Host 'Removed the Galaxy S23 Drawing Tablet firewall rule.'
