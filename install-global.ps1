[CmdletBinding()]
param(
    [ValidateSet("install", "upgrade", "uninstall", "status")]
    [string]$Action = "install",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AdditionalArguments
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$IntegratedInstallerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$IntegratedInstallerPython = $null

$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($launcher) {
    foreach ($version in @("3.12", "3.13", "3.11")) {
        try {
            $candidate = & $launcher.Source "-$version" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate.Trim())) {
                $IntegratedInstallerPython = $candidate.Trim()
                break
            }
        } catch {
            continue
        }
    }
}

if (-not $IntegratedInstallerPython) {
    foreach ($name in @("python3.12.exe", "python3.13.exe", "python3.11.exe", "python.exe")) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $candidate) { continue }
        & $candidate.Source -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $IntegratedInstallerPython = $candidate.Source
            break
        }
    }
}

if (-not $IntegratedInstallerPython) {
    throw "Python 3.11-3.13 was not found. Install Python 3.12 or ask your administrator."
}

& $IntegratedInstallerPython (Join-Path $IntegratedInstallerRoot "install-global.py") $Action @AdditionalArguments
exit $LASTEXITCODE
