@echo off
chcp 65001 > nul
cd /d "%~dp0.."
echo ================================================================
echo   RAG BENCHMARK RUNNER - SYNTHDOCQA (5 FILES ONLY)
echo ================================================================
echo.
echo 1. Chay Smoke Test nhanh (20 cau hoi tren 1 tai lieu nho)
echo 2. Chay danh gia Retrieval toan bo 5 tai lieu (sieu nhanh, khong goi LLM)
echo 3. Chay Benchmark day du (877 cau hoi tren 5 file PDF)
echo 4. Tuy chon tuy chinh
echo.
set /p choice="Chon che do (1/2/3/4): "

if "%choice%"=="1" (
    echo [Dang chay Smoke Test 20 cau hoi...]
    python evaluation\benchmark_synthdocqa.py --doc doc_0000_s1131058660.pdf --sample 20 --top-k 5
) else if "%choice%"=="2" (
    echo [Dang chay danh gia Retrieval tren tat ca 877 cau...]
    python evaluation\benchmark_synthdocqa.py --skip-generation --top-k 5
) else if "%choice%"=="3" (
    echo [Dang chay Benchmark toan dien tren 877 cau...]
    python evaluation\benchmark_synthdocqa.py --top-k 5 --concurrency 4
) else (
    echo Nhap tham so tu do (vi du: --sample 50 --top-k 10):
    set /p custom_args="Tham so: "
    python evaluation\benchmark_synthdocqa.py %custom_args%
)
pause
