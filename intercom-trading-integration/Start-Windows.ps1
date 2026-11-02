param(
    [ValidateSet('setup','start','serve','pin','copy-key','check')]
    [string]$Action = 'check',
    [ValidateSet('guard','oidc')]
    [string]$Role
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Instaleaza Python 3.10+ de pe python.org cu Python Launcher (py), apoi redeschide PowerShell.'
}
$arguments = @('-3', (Join-Path $PSScriptRoot 'windows_setup.py'), $Action)
if ($Role) { $arguments += @('--role', $Role) }
& py @arguments
if ($LASTEXITCODE -ne 0) { throw 'Configurarea/verificarea nu a reusit. Serviciile nu au executat tranzactii reale.' }
