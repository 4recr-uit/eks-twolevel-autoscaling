<#
.SYNOPSIS
    Forward a local port to the Grafana Service in the monitoring namespace.
.EXAMPLE
    .\scripts\port-forward.ps1
.EXAMPLE
    .\scripts\port-forward.ps1 -LocalPort 3001 -Namespace monitoring -ServiceName monitoring-grafana
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$LocalPort = 3000,

    [ValidateNotNullOrEmpty()]
    [string]$Namespace = 'monitoring',

    [ValidateNotNullOrEmpty()]
    [string]$ServiceName = 'monitoring-grafana'
)

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Error 'kubectl was not found. Install it and configure access to the EKS cluster.'
    exit 1
}

Write-Host "Forwarding http://localhost:$LocalPort to service/$ServiceName in namespace $Namespace."
Write-Host 'Wait for the kubectl forwarding message, then open the URL. Press Ctrl+C to stop.'

& kubectl -n $Namespace port-forward --address 127.0.0.1 "service/$ServiceName" "${LocalPort}:80"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Port-forward failed (exit code $LASTEXITCODE). Check your kubeconfig, permissions, Service name, and local port."
    exit $LASTEXITCODE
}
