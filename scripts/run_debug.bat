@echo off
REM ==============================================================================
REM Mini RAG Debug Pipeline Runner (Windows CMD Batch)
REM ==============================================================================
chcp 65001 > nul
setlocal EnableDelayedExpansion

set PROJECT_ROOT=%~dp0..
if "%PROJECT_ROOT:~-1%"=="\" set PROJECT_ROOT=%PROJECT_ROOT:~0,-1%

echo.
echo ================================================================
echo   Mini RAG Debug Pipeline Runner (CMD)
echo ================================================================

set "IMAGE_NAME=mini_rag-ntc_document_rag:latest"

echo [INFO] Thu muc du an: %PROJECT_ROOT%
echo [INFO] Docker Image: %IMAGE_NAME%
echo [INFO] Dang chay debug pipeline trong container...
echo.

docker run --rm -it ^
  --name ntc_debug_pipeline ^
  --env-file "%PROJECT_ROOT%\.env" ^
  -v "%PROJECT_ROOT%/app:/app/app" ^
  -v "%PROJECT_ROOT%/tools:/app/tools" ^
  -v "%PROJECT_ROOT%:/debug_pdf_dir" ^
  %IMAGE_NAME% ^
  python /app/tools/debug_pipeline.py "/debug_pdf_dir"

echo.
echo ================================================================
echo   Debug Pipeline hoan thanh!
echo ================================================================
