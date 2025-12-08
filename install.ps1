Write-Host "=== SAYF CONTEST SYSTEM INSTALLER ===" -ForegroundColor Cyan

# 1. Detect Python
Write-Host "`n[1] Detecting Python interpreter..." -ForegroundColor Yellow

$python = Get-Command python -ErrorAction SilentlyContinue
$py = Get-Command py -ErrorAction SilentlyContinue
$custom = "C:\Users\Achraf\AppData\Local\Programs\Python\Python313\python.exe"

if (Test-Path $custom) {
    $pythonExec = $custom
    Write-Host "Using Python 3.13 at: $pythonExec" -ForegroundColor Green
}
elseif ($python) {
    $pythonExec = $python.Source
    Write-Host "Using: $pythonExec" -ForegroundColor Green
}
elseif ($py) {
    $pythonExec = "py"
    Write-Host "Using Windows py launcher" -ForegroundColor Green
}
else {
    Write-Host "ERROR: No Python installation detected." -ForegroundColor Red
    exit 1
}

# 2. Check pip
Write-Host "`n[2] Checking pip..." -ForegroundColor Yellow
pipCheck = & $pythonExec -m pip --version 2>$null
if (-not $pipCheck) {
    Write-Host "pip missing. Attempting installation..." -ForegroundColor Red
    & $pythonExec -m ensurepip --default-pip
}

# 3. Upgrade pip
Write-Host "`n[3] Upgrading pip..." -ForegroundColor Yellow
& $pythonExec -m pip install --upgrade pip

# 4. Install required packages
Write-Host "`n[4] Installing Flask, qrcode, Pillow..." -ForegroundColor Yellow
& $pythonExec -m pip install flask qrcode Pillow

# 5. Install requirements.txt if present
if (Test-Path ".\requirements.txt") {
    Write-Host "`n[5] Installing requirements.txt..." -ForegroundColor Yellow
    & $pythonExec -m pip install -r requirements.txt
} else {
    Write-Host "`nNo requirements.txt found — skipping." -ForegroundColor DarkYellow
}

# 6. Final check
Write-Host "`n[6] Verifying installation..." -ForegroundColor Yellow
try {
    & $pythonExec - << 'EOF'
import flask, qrcode, PIL
print("SUCCESS: All modules installed correctly.")
EOF
    Write-Host "`n=== INSTALLATION COMPLETE ===" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: One or more modules failed to import." -ForegroundColor Red
}
