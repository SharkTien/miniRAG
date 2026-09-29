param(
    [string]$PdfFile = "",
    [switch]$Rebuild = $false
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Mini RAG Debug Pipeline Runner" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# Rebuild image neu duoc yeu cau
if ($Rebuild) {
    Write-Host "`n[BUILD] Dang build Docker image..." -ForegroundColor Yellow
    docker compose build ntc_document_rag
}

# Xac dinh file PDF
if ([string]::IsNullOrWhiteSpace($PdfFile)) {
    $found = Get-ChildItem -Path $ProjectRoot -Filter "*.pdf" -File | Where-Object { $_.Name -like "*HR-01*" } | Select-Object -First 1
    if (-not $found) {
        $found = Get-ChildItem -Path $ProjectRoot -Filter "*.pdf" -File | Select-Object -First 1
    }
    if ($found) {
        $PdfFile = $found.FullName
    }
}

if (-not (Test-Path -LiteralPath $PdfFile)) {
    Write-Host "[ERROR] Khong tim thay file PDF: $PdfFile" -ForegroundColor Red
    Write-Host "Cach dung: .\scripts\run_debug.ps1 -PdfFile 'duong_dan_den_file.pdf'" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n[INFO] File PDF: $PdfFile" -ForegroundColor Green
$PdfDir = Split-Path -Parent $PdfFile
$PdfName = Split-Path -Leaf $PdfFile

# Kiem tra Docker image
$ImageName = "mini_rag-ntc_document_rag:latest"
$checkImage = docker images -q $ImageName 2>$null
if (-not $checkImage) {
    $altImage = docker images -q "mini_rag_ntc_document_rag:latest" 2>$null
    if ($altImage) {
        $ImageName = "mini_rag_ntc_document_rag:latest"
    } else {
        Write-Host "[INFO] Image chua co san, dang build..." -ForegroundColor Yellow
        docker compose build ntc_document_rag
    }
}

Write-Host "[INFO] Docker Image: $ImageName" -ForegroundColor Cyan

# Kiem tra file .env
$EnvParams = @()
$EnvPath = Join-Path $ProjectRoot ".env"
if (Test-Path -LiteralPath $EnvPath) {
    $EnvParams += "--env-file"
    $EnvParams += $EnvPath
}

Write-Host "[INFO] Dang khoi chay debug pipeline trong container..." -ForegroundColor Yellow
Write-Host ""

# Chay debug pipeline
$dockerArgs = @(
    "run", "--rm",
    "--name", "ntc_debug_pipeline",
    "-v", "${ProjectRoot}/app:/app/app",
    "-v", "${ProjectRoot}/tools:/app/tools",
    "-v", "${PdfDir}:/debug_pdf_dir"
) + $EnvParams + @(
    $ImageName,
    "python", "/app/tools/debug_pipeline.py", "/debug_pdf_dir/$PdfName"
)

& docker @dockerArgs

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Debug Pipeline ket thuc!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
