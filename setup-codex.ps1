[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$OldLocation = Get-Location
$TempDir = $null
$Locked = $false
$SavedEnv = @{}
$Names = @(
    'UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','UV_PYTHON_BIN_DIR','UV_TOOL_DIR','UV_TOOL_BIN_DIR',
    'UV_PYTHON_PREFERENCE','UV_PYTHON_INSTALL_REGISTRY','UV_PYTHON_INSTALL_BIN','UV_NO_CONFIG',
    'PYTHONUTF8','PIXI_HOME','PIXI_CACHE_DIR','PIXI_NO_PATH_UPDATE','PIXI_COLOR','PIXI_NO_PROGRESS','PATH'
)
foreach ($Name in $Names) { $SavedEnv[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process') }
function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "SETUP_BLOCKED: $Step failed (exit $LASTEXITCODE)." }
}
function Set-QualityPath {
    $env:PIXI_HOME = Join-Path $Root '.bootstrap\pixi-home'
    $env:PIXI_CACHE_DIR = Join-Path $Root '.bootstrap\pixi-cache'
    $env:PIXI_NO_PATH_UPDATE = '1'
    $env:PIXI_COLOR = 'never'
    $env:PIXI_NO_PROGRESS = 'true'
    $env:PYTHONUTF8 = '1'
    $QualityPaths = @(
        (Join-Path $Root '.bootstrap\pixi-home\bin'),
        (Join-Path $Root '.bootstrap\libreoffice\program')
    )
    $env:PATH = (($QualityPaths + @($env:PATH)) -join [IO.Path]::PathSeparator)
}
try {
    Set-Location -LiteralPath $Root
    if (-not (Test-Path -LiteralPath '.classroom-project.json')) {
        throw 'SETUP_BLOCKED: incomplete project.'
    }
    foreach ($Dir in @('.bootstrap','.venv','.skill-work')) {
        if (Test-Path -LiteralPath $Dir) {
            if ((Get-Item -LiteralPath $Dir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "SETUP_BLOCKED: $Dir is a link/junction."
            }
        }
    }
    $Python = Join-Path $Root '.venv\Scripts\python.exe'
    $Quality = Join-Path $Root '.agents\skills\medical-journal-to-pptx-classroom\scripts\quality_tools.py'
    Set-QualityPath

    if ($CheckOnly) {
        & $Python $Quality check --json
        Assert-Exit 'Full-quality tools check'
        & $Python (Join-Path $Root 'tools\codex_setup.py') --check
        Assert-Exit 'Readiness check'
    } else {
        New-Item -ItemType Directory -Force -Path '.bootstrap','.skill-work' | Out-Null
        New-Item -ItemType Directory -Path '.bootstrap\setup.lock' -ErrorAction Stop | Out-Null
        $Locked = $true
        $Receipt = '.skill-work\codex-setup.json'
        if (Test-Path -LiteralPath $Receipt) {
            if ((Get-Item -LiteralPath $Receipt -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'SETUP_BLOCKED: receipt is a link.'
            }
            Remove-Item -LiteralPath $Receipt
        }

        $env:UV_CACHE_DIR = Join-Path $Root '.bootstrap\cache'
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $Root '.bootstrap\python'
        $env:UV_PYTHON_BIN_DIR = Join-Path $Root '.bootstrap\python-bin'
        $env:UV_TOOL_DIR = Join-Path $Root '.bootstrap\tools'
        $env:UV_TOOL_BIN_DIR = Join-Path $Root '.bootstrap\tool-bin'
        $env:UV_PYTHON_INSTALL_REGISTRY = 'false'
        $env:UV_PYTHON_INSTALL_BIN = 'false'
        $env:UV_PYTHON_PREFERENCE = 'only-managed'
        $env:UV_NO_CONFIG = '1'

        $DependenciesReady = $false
        if (Test-Path -LiteralPath '.venv') {
            if (-not (Test-Path -LiteralPath $Python)) {
                throw 'SETUP_BLOCKED: incomplete .venv; it was not removed.'
            }
            & $Python -c 'import sys; raise SystemExit(not ((3,11)<=sys.version_info[:2]<=(3,13)))'
            Assert-Exit 'Existing .venv Python compatibility'
            & $Python (Join-Path $Root 'tools\codex_setup.py') --dependencies-ready
            $DependenciesReady = $LASTEXITCODE -eq 0
        }

        if (-not $DependenciesReady) {
            Write-Host 'Preparing project-local Python tooling. Internet approval may be required.'
            $Arch = $env:PROCESSOR_ARCHITECTURE
            if ($env:PROCESSOR_ARCHITEW6432) { $Arch = $env:PROCESSOR_ARCHITEW6432 }
            switch ($Arch.ToUpperInvariant()) {
                'AMD64' { $Target = 'x86_64-pc-windows-msvc'; $Hash = '5049375aa2a5162f132b2c1cb992e25d42d47d934cab8c174dbe6f60973dcc12' }
                'ARM64' { $Target = 'aarch64-pc-windows-msvc'; $Hash = 'dbb3a5bd06d20c9ab8bb9a79c7c4fb5832ca1c7ba5f231a020bc92e5a3c6dcf4' }
                default { throw 'SETUP_BLOCKED: only 64-bit Windows bootstrap is provided.' }
            }
            $TempDir = Join-Path $Root ('.bootstrap\download-' + [Guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $TempDir | Out-Null
            $Archive = Join-Path $TempDir 'uv.zip'
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/0.8.22/uv-$Target.zip" -OutFile $Archive
            $Actual = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($Actual -ne $Hash) { throw 'SETUP_BLOCKED: uv checksum mismatch; nothing executed.' }
            Expand-Archive -LiteralPath $Archive -DestinationPath (Join-Path $TempDir 'unpacked')
            $Binaries = @(Get-ChildItem -LiteralPath (Join-Path $TempDir 'unpacked') -Recurse -Filter 'uv.exe' -File)
            if ($Binaries.Count -ne 1) { throw 'SETUP_BLOCKED: unexpected verified uv archive layout.' }
            $Uv = $Binaries[0].FullName
            if (-not (Test-Path -LiteralPath '.venv')) {
                & $Uv --no-config venv --python 3.12 --seed (Join-Path $Root '.venv')
                Assert-Exit 'Managed Python and venv creation'
            }
            & $Uv --no-config pip install --python $Python --only-binary ':all:' --requirement (Join-Path $Root 'requirements.txt')
            Assert-Exit 'Project dependencies'
        } else {
            Write-Host 'Reusing this project Python environment.'
        }

        Write-Host 'Preparing fixed LibreOffice and Poppler rendering tools inside this project.'
        & $Python $Quality install --json
        Assert-Exit 'Full-quality rendering tools'
        & $Python (Join-Path $Root 'tools\codex_setup.py') --check
        Assert-Exit 'Readiness check'
    }
} finally {
    if ($TempDir -and (Test-Path -LiteralPath $TempDir)) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force
    }
    if ($Locked) {
        Remove-Item -LiteralPath (Join-Path $Root '.bootstrap\setup.lock') -ErrorAction SilentlyContinue
    }
    foreach ($Name in $Names) {
        [Environment]::SetEnvironmentVariable($Name, $SavedEnv[$Name], 'Process')
    }
    Set-Location -LiteralPath $OldLocation
}
