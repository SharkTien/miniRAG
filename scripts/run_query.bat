@echo off
REM ==============================================================================
REM Mini RAG Phase 2: RAG Query Runner (Windows CMD)
REM ==============================================================================
chcp 65001 > nul
setlocal EnableDelayedExpansion

set PROJECT_ROOT=%~dp0..
if "%PROJECT_ROOT:~-1%"=="\" set PROJECT_ROOT=%PROJECT_ROOT:~0,-1%

set "IMAGE_NAME=mini_rag-ntc_document_rag:latest"

docker run --rm -it ^
  --name ntc_query_runner ^
  --env-file "%PROJECT_ROOT%\.env" ^
  -v "%PROJECT_ROOT%/app:/app/app" ^
  -v "%PROJECT_ROOT%/tests:/app/tests" ^
  %IMAGE_NAME% ^
  python /app/tests/test_query_rag.py %*
