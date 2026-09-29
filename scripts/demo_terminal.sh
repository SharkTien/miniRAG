#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${RAG_BASE_URL:-http://localhost:41873}"
FILE_PATH="${1:-}"
shift || true
QUESTION="$*"

if [[ -z "$FILE_PATH" || -z "$QUESTION" || ! -f "$FILE_PATH" ]]; then
    echo "Usage: $0 <file-path> <question>" >&2
    exit 2
fi

echo "[1/6] Checking API"
curl -fsS "$BASE_URL/health"
echo

echo "[2/6] Uploading file: $FILE_PATH"
upload_response="$(curl -fsS -X POST "$BASE_URL/documents" -F "files=@$FILE_PATH")"
printf '%s\n' "$upload_response" | python -m json.tool

document_id="$(printf '%s' "$upload_response" | python -c \
    'import json, sys; print(json.load(sys.stdin)["documents"][0]["id"])')"

echo "[3/6] Waiting for ingestion: $document_id"
for attempt in $(seq 1 90); do
    document_response="$(curl -fsS "$BASE_URL/documents?page=1&size=100&filter=all")"
    status="$(printf '%s' "$document_response" | python -c \
        'import json, sys; data=json.load(sys.stdin); wanted=sys.argv[1]; rows=data.get("documents", []); row=next((item for item in rows if item.get("id") == wanted), {}); print(row.get("status", "missing"))' \
        "$document_id")"
    echo "  attempt=$attempt status=$status"

    case "$status" in
        processed) break ;;
        failed|cancelled)
            printf '%s\n' "$document_response" | python -m json.tool
            exit 1
            ;;
    esac

    if [[ "$attempt" == "90" ]]; then
        echo "Ingestion timed out." >&2
        exit 1
    fi
    sleep 2
done

echo "[4/6] Creating a conversation"
conversation_response="$(curl -fsS -X POST "$BASE_URL/api/conversations" \
    -H 'Content-Type: application/json' -d '{}')"
conversation_id="$(printf '%s' "$conversation_response" | python -c \
    'import json, sys; print(json.load(sys.stdin)["id"])')"
echo "conversation_id=$conversation_id"

echo "[5/6] Asking RAG: $QUESTION"
message_response="$(python -c 'import json,sys; print(json.dumps({"question": " ".join(sys.argv[1:]), "top_k": 5}))' "$QUESTION" | \
    curl -fsS -X POST "$BASE_URL/api/conversations/$conversation_id/messages" \
    -H 'Content-Type: application/json' -d @-)"
printf '%s\n' "$message_response" | python -m json.tool

echo "[6/6] Reading persisted conversation history"
curl -fsS "$BASE_URL/api/conversations/$conversation_id" | python -m json.tool
