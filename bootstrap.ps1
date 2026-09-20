$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Test-Python([string]$exe, [string[]]$args = @()) {
    try {
        $probeArgs = @($args) + @('-c', 'import sys,venv; assert (3,11) <= sys.version_info[:2] < (3,14); print(sys.executable)')
        $out = & $exe @probeArgs 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            return [pscustomobject]@{ Exe = $exe; Args = $args; Display = (($exe + ' ' + ($args -join ' ')).Trim()) }
        }
    } catch {}
    return $null
}

function Find-Python {
    # Prefer concrete python.exe paths. This avoids the Windows Store/App Installer
    # 'py' shim claiming a version that is not actually installed.
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python313\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) {
            $r = Test-Python $p
            if ($r) { return $r }
        }
    }

    foreach ($cmd in @('python', 'python3')) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) {
            $r = Test-Python $found.Source
            if ($r) { return $r }
        }
    }

    # Old and new Python launcher variants. Only accept them after a real probe.
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($sel in @('-3.12', '-3.13', '-3.11')) {
            $r = Test-Python $py.Source @($sel)
            if ($r) { return $r }
        }
    }
    return $null
}

function Invoke-Python($py, [string[]]$arguments) {
    & $py.Exe @($py.Args + $arguments)
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE" }
}

$py = Find-Python
if (-not $py) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'Python 3.11-3.13 was not found and winget is unavailable. Install Python 3.12 and run Eidolarch again.'
    }

    Write-Host '[Eidolarch] Python not found. Installing Python 3.12 for the current user...'
    & winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget failed with exit code $LASTEXITCODE" }

    # Winget may not refresh PATH in the current process, therefore probe explicit paths again.
    $py = Find-Python
    if (-not $py) {
        throw 'Python 3.12 was installed, but Eidolarch could not locate python.exe. Close this window and run run.bat again.'
    }
}

Write-Host "[Eidolarch] Using Python: $($py.Display)"
Invoke-Python $py @('-c', 'import sys; print(sys.version.split()[0]); print(sys.executable)')

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host '[Eidolarch] Creating virtual environment...'
    Invoke-Python $py @('-m', 'venv', '.venv')
}

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { throw 'Virtual environment was not created correctly.' }


function Invoke-VenvPip([string[]]$arguments, [switch]$AllowFailure) {
    # pip legitimately writes warnings and progress to stderr. Windows PowerShell 5
    # may promote any native stderr line to NativeCommandError when
    # ErrorActionPreference=Stop, even when pip itself succeeds. Run pip with a
    # relaxed preference and decide success strictly by its exit code.
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $venvPy -m pip @arguments
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "pip failed with exit code $code"
    }
    return $code
}

function Test-VenvPythonCode([string]$code) {
    # External programs may write normal probe errors (for example ModuleNotFoundError)
    # to stderr. With ErrorActionPreference=Stop PowerShell can turn that into a
    # terminating NativeCommandError before we get a chance to inspect LASTEXITCODE.
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $venvPy -c $code 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $oldPreference
    }
}


function Test-TorchStack {
    return Test-VenvPythonCode 'import torch, torchvision; from transformers import AutoImageProcessor; print(torch.__version__); print(torchvision.__version__)'
}

function Install-TorchStack([string]$indexUrl) {
    Write-Host "[Eidolarch] Installing matched torch + torchvision from $indexUrl ..."
    Invoke-VenvPip @('install', '--upgrade', '--force-reinstall', 'torch', 'torchvision', '--index-url', $indexUrl) | Out-Null
}

$depsMarker = '.venv\.eidolarch_deps_v8'
if (-not (Test-Path $depsMarker)) {
    Write-Host '[Eidolarch] Installing application dependencies...'
    Invoke-VenvPip @('install', '--upgrade', 'pip') | Out-Null
    Invoke-VenvPip @('install', '-r', 'requirements.txt') | Out-Null
    Set-Content -Path $depsMarker -Value 'ok' -Encoding Ascii
}

# Prefer CUDA when an NVIDIA GPU is present. A CPU fallback is still allowed.
$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
$torchPresent = Test-VenvPythonCode 'import torch'
$cudaReady = $false
if ($torchPresent) {
    $cudaReady = Test-VenvPythonCode 'import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)'
}

if ($nvidia) {
    if (-not $cudaReady) {
        if (-not $torchPresent) {
            Write-Host '[Eidolarch] PyTorch is not installed yet.'
        } else {
            Write-Host '[Eidolarch] NVIDIA GPU detected, but current PyTorch cannot use CUDA.'
        }
        Write-Host '[Eidolarch] Installing CUDA-enabled PyTorch (this download is large)...'
        if ($torchPresent) {
            Invoke-VenvPip @('uninstall', '-y', 'torch', 'torchvision', 'torchaudio') | Out-Null
        }

        # Try the current CUDA wheel first, then a slightly older wheel for driver compatibility.
        $cudaInstallCode = Invoke-VenvPip @('install', '--upgrade', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cu128') -AllowFailure
        if ($cudaInstallCode -ne 0) {
            Write-Warning 'CUDA 12.8 PyTorch installation failed. Trying CUDA 12.6 build...'
            Invoke-VenvPip @('install', '--upgrade', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cu126') | Out-Null
        }

        $cudaReady = Test-VenvPythonCode 'import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)'
        if (-not $cudaReady) {
            Write-Warning 'PyTorch was installed, but CUDA is still unavailable. Eidolarch will run on CPU. Updating the NVIDIA driver may be required.'
            if (-not (Test-VenvPythonCode 'import torch')) {
                Write-Host '[Eidolarch] Installing CPU PyTorch fallback...'
                Invoke-VenvPip @('install', '--upgrade', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cpu') | Out-Null
            }
        }
    }
} elseif (-not $torchPresent) {
    Write-Host '[Eidolarch] NVIDIA GPU not detected. Installing CPU PyTorch...'
    Invoke-VenvPip @('install', '--upgrade', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cpu') | Out-Null
}


# The object detector depends on torchvision through Transformers AutoImageProcessor.
# Repair older environments where bootstrap installed torch but left torchvision absent/incompatible.
if (-not (Test-TorchStack)) {
    Write-Warning '[Eidolarch] torch/torchvision stack is missing or incompatible. Repairing it now...'
    if ($nvidia) {
        $repairCode = Invoke-VenvPip @('install', '--upgrade', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cu128') -AllowFailure
        if ($repairCode -ne 0) {
            Write-Warning '[Eidolarch] CUDA 12.8 stack repair failed. Trying CUDA 12.6...'
            $repairCode = Invoke-VenvPip @('install', '--upgrade', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cu126') -AllowFailure
        }
        if ($repairCode -ne 0) {
            Write-Warning '[Eidolarch] CUDA stack repair failed. Falling back to CPU torch + torchvision.'
            Invoke-VenvPip @('install', '--upgrade', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cpu') | Out-Null
        }
    } else {
        Invoke-VenvPip @('install', '--upgrade', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cpu') | Out-Null
    }
}
if (-not (Test-TorchStack)) {
    throw 'Eidolarch could not import torch + torchvision + AutoImageProcessor after repair. See the console output above.'
}

Write-Host '[Eidolarch] Runtime check:'
# Avoid quoted string literals in the -c payload. Windows PowerShell 5/native
# argument quoting may otherwise strip embedded quotes before python.exe sees them.
& $venvPy -c 'import torch, torchvision; from transformers import AutoImageProcessor; print(torch.__name__, torch.__version__); print(torchvision.__name__, torchvision.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else None); print(AutoImageProcessor.__name__)'
if ($LASTEXITCODE -ne 0) { throw "Runtime check failed with exit code $LASTEXITCODE" }

$requiredSourceFiles = @(
    'photomind\__init__.py',
    'photomind\app.py',
    'photomind\config.py',
    'photomind\db.py',
    'photomind\static\index.html'
)
$missingSourceFiles = @($requiredSourceFiles | Where-Object { -not (Test-Path $_) })
if ($missingSourceFiles.Count -gt 0) {
    throw ("Eidolarch source tree is incomplete. Missing: " + ($missingSourceFiles -join ', ') + ". If this is a Git working copy, run: git restore photomind")
}

& $venvPy launcher.py
exit $LASTEXITCODE
