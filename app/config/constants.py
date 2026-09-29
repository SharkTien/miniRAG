"""Immutable application constants shared by the backend packages."""

from __future__ import annotations


# Single-tenant storage actor. This is metadata, not an application user.
SYSTEM_ACTOR = "system"

# Upload and storage defaults
DEFAULT_MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DEFAULT_MINIO_BUCKET = "documents"
ALLOWED_EXTENSIONS = frozenset(
    {".pdf", ".png", ".jpeg", ".jpg", ".txt", ".csv", ".markdown", ".docx", ".pptx", ".xlsx"}
)

# Retrieval defaults
DEFAULT_EMBEDDING_DIM = 2048
DEFAULT_TOP_K = 10
DEFAULT_SIMILARITY_THRESHOLD = 0.2

# Qwen semantic-normalization policy
DEFAULT_QWEN_BASE_URL = "http://host.docker.internal:8027/v1"
DEFAULT_QWEN_MODEL = "a2genesis/Qwen3.8-27B-NVFP4"
DEFAULT_QWEN_TIMEOUT_SECONDS = 180
DEFAULT_QWEN_MAX_INPUT_CHARS = 16000
QWEN_MAX_RETRIES = 2
QWEN_TEMPERATURE = 0.0
QWEN_MAX_OUTPUT_TOKENS = 4096
QWEN_RETRY_DELAY_SECONDS = 0.5
QWEN_FUZZY_LENGTH_DELTA = 2
QWEN_FUZZY_MATCH_THRESHOLD = 0.72
QWEN_MAX_EXPANSION_RATIO = 1.25
QWEN_MAX_EXPANSION_CHARS = 300
QWEN_MAX_NOVEL_TOKEN_RATIO = 0.30
