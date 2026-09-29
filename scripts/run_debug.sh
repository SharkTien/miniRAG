#!/usr/bin/env bash
# ==============================================================================
# Mini RAG Debug Pipeline Runner (Bash / Git Bash / Linux / WSL)
# ==============================================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PDF_FILE="$1"

echo ""
echo "================================================================"
echo "  Mini RAG Debug Pipeline Runner (Bash Terminal)"
echo "================================================================"

# Tìm file PDF nếu không truyền tham số
if [ -z "$PDF_FILE" ]; then
    PDF_FILE=$(find . -maxdepth 1 -type f -name "*HR-01*.pdf" | head -n 1)
    if [ -z "$PDF_FILE" ]; then
        PDF_FILE=$(find . -maxdepth 1 -type f -name "*.pdf" | head -n 1)
    fi
fi

if [ ! -f "$PDF_FILE" ]; then
    echo "[ERROR] Không tìm thấy file PDF: $PDF_FILE"
    echo "Cách dùng: ./scripts/run_debug.sh path/to/your.pdf"
    exit 1
fi

PDF_NAME=$(basename "$PDF_FILE")
PDF_DIR="$(cd "$(dirname "$PDF_FILE")" && pwd)"

IMAGE_NAME="mini_rag-ntc_document_rag:latest"
if ! docker image inspect "$IMAGE_NAME" > /dev/null 2>&1; then
    IMAGE_NAME="mini_rag_ntc_document_rag:latest"
fi

echo "[INFO] PDF: $PDF_FILE"
echo "[INFO] Docker Image: $IMAGE_NAME"
echo "[INFO] Đang chạy debug pipeline trong container..."
echo ""

ENV_ARGS=()
if [ -f "$PROJECT_ROOT/.env" ]; then
    ENV_ARGS+=("--env-file" "$PROJECT_ROOT/.env")
fi

docker run --rm \
    --name ntc_debug_pipeline \
    -v "$PROJECT_ROOT/app:/app/app" \
    -v "$PROJECT_ROOT/tools:/app/tools" \
    -v "$PDF_DIR:/debug_pdf_dir" \
    "${ENV_ARGS[@]}" \
    "$IMAGE_NAME" \
    python /app/tools/debug_pipeline.py "/debug_pdf_dir/$PDF_NAME"

echo ""
echo "================================================================"
echo "  Debug Pipeline hoàn thành!"
echo "================================================================"
