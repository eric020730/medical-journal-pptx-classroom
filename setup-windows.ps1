[CmdletBinding()]
param(
    [switch]$SkipSystem,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$env:PYTHONUTF8 = "1"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Find-CompatiblePython {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($minor in @("3.12", "3.13", "3.11")) {
            try {
                $result = & $launcher.Source "-$minor" -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $result -and (Test-Path -LiteralPath $result)) {
                    return $result.Trim()
                }
            } catch {
                continue
            }
        }
    }

    $candidates = @()
    foreach ($name in @("python3.12.exe", "python3.13.exe", "python3.11.exe", "python.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += $command.Source
        }
    }
    foreach ($minor in @("312", "313", "311")) {
        if ($env:LOCALAPPDATA) {
            $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$minor\python.exe"
        }
        if ($env:ProgramFiles) {
            $candidates += Join-Path $env:ProgramFiles "Python$minor\python.exe"
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        try {
            & $candidate -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            continue
        }
    }
    return $null
}

function Invoke-WingetInstall {
    param([string]$PackageId, [string]$Description)
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Windows Package Manager (winget) is missing. Install Microsoft App Installer or ask your administrator."
    }

    Write-Step "Installing $Description ($PackageId). Windows may request approval."
    & $winget.Source install --id $PackageId --exact --source winget `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $Description (exit code $LASTEXITCODE)."
    }
    Refresh-ProcessPath
}

function Test-LibreOffice {
    if (Get-Command soffice.exe -ErrorAction SilentlyContinue) {
        return $true
    }
    foreach ($base in @(${env:ProgramW6432}, ${env:ProgramFiles}, ${env:ProgramFiles(x86)})) {
        if ($base -and (Test-Path -LiteralPath (Join-Path $base "LibreOffice\program\soffice.exe"))) {
            return $true
        }
    }
    return $false
}

function Test-Poppler {
    if (Get-Command pdftoppm.exe -ErrorAction SilentlyContinue) {
        return $true
    }
    if ($env:LOCALAPPDATA) {
        $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        if (Test-Path -LiteralPath $wingetRoot) {
            $found = Get-ChildItem -LiteralPath $wingetRoot -Filter "pdftoppm.exe" `
                -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                return $true
            }
        }
    }
    return $false
}

Refresh-ProcessPath
$bootstrapPython = Find-CompatiblePython
if (-not $bootstrapPython) {
    if ($SkipSystem) {
        throw "Python 3.11-3.13 is not installed. Install Python 3.12 or run setup-windows.cmd without -SkipSystem."
    }
    Invoke-WingetInstall -PackageId "Python.Python.3.12" -Description "Python 3.12"
    $bootstrapPython = Find-CompatiblePython
    if (-not $bootstrapPython) {
        throw "Python was installed but is not yet visible. Close this window, reopen setup-windows.cmd, and retry."
    }
}

if (-not $SkipSystem) {
    if (-not (Test-LibreOffice)) {
        Invoke-WingetInstall -PackageId "TheDocumentFoundation.LibreOffice" -Description "LibreOffice"
    } else {
        Write-Step "LibreOffice is already installed."
    }

    if (-not (Test-Poppler)) {
        Invoke-WingetInstall -PackageId "oschwartz10612.Poppler" -Description "Poppler PDF tools"
    } else {
        Write-Step "Poppler is already installed."
    }
}

Write-Step "Using Python: $bootstrapPython"
$projectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $projectPython)) {
    & $bootstrapPython -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create the project Python environment."
    }
}

Write-Step "Installing required Python packages."
& $projectPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Unable to update pip. Check your internet connection and proxy settings."
}
& $projectPython -m pip install --requirement (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install the required Python packages."
}

foreach ($directory in @("sample-papers", "outputs", ".skill-work")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $directory) | Out-Null
}

$classroom = Join-Path $ProjectRoot "tools\classroom.py"
Write-Step "Generating the fictional practice article."
& $projectPython $classroom demo
if ($LASTEXITCODE -ne 0) {
    throw "Unable to create the synthetic classroom PDF."
}

Write-Step "Checking the local environment."
if ($SkipSystem) {
    & $projectPython $classroom doctor
} else {
    & $projectPython $classroom doctor --strict
}
if ($LASTEXITCODE -ne 0) {
    throw "The environment check failed. Review the missing items above."
}

if (-not $SkipSmoke) {
    Write-Step "Running an end-to-end PDF-to-PowerPoint smoke test."
    & $projectPython $classroom smoke-test
    if ($LASTEXITCODE -ne 0) {
        throw "The classroom smoke test failed."
    }
}

Write-Step "Installation complete."
Write-Host "1. Open this project folder in the ChatGPT/Codex desktop app."
Write-Host "2. Add a PDF or choose sample-papers\classroom-demo-paper.pdf."
Write-Host '3. Start a task with: $medical-journal-to-pptx-classroom'
Write-Host "4. Find finished presentations in: $(Join-Path $ProjectRoot 'outputs')"
