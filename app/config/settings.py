import os
from pathlib import Path

from app.config.constants import (
    ALLOWED_EXTENSIONS as DEFAULT_ALLOWED_EXTENSIONS,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_MAX_UPLOAD_BYTES,
    DEFAULT_MINIO_BUCKET,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TOP_K,
    DEFAULT_QWEN_BASE_URL,
    DEFAULT_QWEN_MAX_INPUT_CHARS,
    DEFAULT_QWEN_MODEL,
    DEFAULT_QWEN_TIMEOUT_SECONDS,
)

try:
    from dotenv import load_dotenv
    # Load .env from project root if it exists
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rag:rag@postgres:5432/rag")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", DEFAULT_MINIO_BUCKET)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES)))
ALLOWED_EXTENSIONS = DEFAULT_ALLOWED_EXTENSIONS
DOCLING_DO_OCR = os.getenv("DOCLING_DO_OCR", "auto").lower()
DOCLING_DO_TABLE_STRUCTURE = os.getenv("DOCLING_DO_TABLE_STRUCTURE", "false").lower() == "true"
DOCLING_DEVICE = os.getenv("DOCLING_DEVICE", "cpu")
DOCLING_NUM_THREADS = int(os.getenv("DOCLING_NUM_THREADS", "4"))
DOCLING_OCR_BATCH_SIZE = int(os.getenv("DOCLING_OCR_BATCH_SIZE", "4"))
DOCLING_FORCE_FULL_PAGE_OCR = os.getenv("DOCLING_FORCE_FULL_PAGE_OCR", "true").lower() == "true"
DOCLING_OCR_ENGINE = os.getenv("DOCLING_OCR_ENGINE", "tesseract").lower()
DOCLING_TESSERACT_PSM = int(os.getenv("DOCLING_TESSERACT_PSM", "6"))
DOCLING_TESSERACT_OSD = os.getenv("DOCLING_TESSERACT_OSD", "false").lower() == "true"
DOCLING_OCR_LANG = [
    value.strip()
    for value in os.getenv("DOCLING_OCR_LANG", "vie,eng").split(",")
    if value.strip()
]
EXTRACTION_TIMEOUT_SECONDS = int(os.getenv("EXTRACTION_TIMEOUT_SECONDS", "1800"))

# NVIDIA NIM & Semantic Normalization Configuration
NGC_API_KEY = (os.getenv("NGC_API_KEY") or os.getenv("NVIDIA_API_KEY") or "").strip()
NIM_BASE_URL = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
NIM_MODEL = os.getenv("NIM_MODEL", "meta/llama-3.2-11b-vision-instruct")
NIM_CONCURRENCY = int(os.getenv("NIM_CONCURRENCY", "4"))
NIM_TIMEOUT_SECONDS = int(os.getenv("NIM_TIMEOUT_SECONDS", "120"))
NIM_MAX_INPUT_CHARS = int(os.getenv("NIM_MAX_INPUT_CHARS", "16000"))
ENABLE_NIM_NORMALIZATION = os.getenv("ENABLE_NIM_NORMALIZATION", "false").lower() == "true"

# OCR/semantic routing.  Keep ENABLE_NIM_NORMALIZATION as a backwards-
# compatible switch, but prefer the provider policy below for new deployments.
SEMANTIC_NORMALIZER = os.getenv(
    "SEMANTIC_NORMALIZER",
    "nvidia" if ENABLE_NIM_NORMALIZATION else "none",
).strip().lower()
SEMANTIC_NORMALIZE_OCR_ONLY = os.getenv(
    "SEMANTIC_NORMALIZE_OCR_ONLY", "true"
).lower() == "true"
SEMANTIC_OCR_CONFIDENCE_GATE = float(
    os.getenv("SEMANTIC_OCR_CONFIDENCE_GATE", "0.93")
)

# Existing PP-OCRv6 service (OpenAPI: POST /v1/ocr).  This project does not own
# that container; auto routing falls back to Docling/Tesseract when unavailable.
LOCAL_OCR_BASE_URL = os.getenv(
    "LOCAL_OCR_BASE_URL", "http://host.docker.internal:8012"
).rstrip("/")
LOCAL_OCR_TIMEOUT_SECONDS = int(os.getenv("LOCAL_OCR_TIMEOUT_SECONDS", "180"))
LOCAL_OCR_DPI = int(os.getenv("LOCAL_OCR_DPI", "180"))
LOCAL_OCR_BATCH_SIZE = max(1, int(os.getenv("LOCAL_OCR_BATCH_SIZE", "2")))
TESSERACT_PAGE_CONCURRENCY = max(
    1, int(os.getenv("TESSERACT_PAGE_CONCURRENCY", "4"))
)
TESSERACT_PAGE_TIMEOUT_SECONDS = int(
    os.getenv("TESSERACT_PAGE_TIMEOUT_SECONDS", "90")
)
# Hugging Face Token Configuration (từ HF_KEY hoặc HF_TOKEN)
HF_TOKEN = (os.getenv("HF_TOKEN") or os.getenv("HF_KEY") or os.getenv("HUGGING_FACE_HUB_TOKEN") or "").strip()
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN
    os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN

EXTRACTION_PAGE_CONCURRENCY = int(os.getenv("EXTRACTION_PAGE_CONCURRENCY", "2"))
PERSIST_PAGE_VISUALS = os.getenv("PERSIST_PAGE_VISUALS", "true").lower() == "true"
PAGE_VISUAL_SCALE = max(0.75, float(os.getenv("PAGE_VISUAL_SCALE", "1.5")))

# RAGFlow & DeepDoc Configuration
DOCUMENT_PARSER_ENGINE = os.getenv("DOCUMENT_PARSER_ENGINE", "auto").lower()  # auto, ppocr, ragflow, docling
RAGFLOW_MODE = os.getenv("RAGFLOW_MODE", "deepdoc").lower()  # "deepdoc" (in-process engine) or "api" (remote server)
RAGFLOW_BASE_URL = os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380").rstrip("/")
RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY", "").strip()

# Embedding & Retrieval (RAG) Configuration
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM)))
TOP_K = int(os.getenv("TOP_K", str(DEFAULT_TOP_K)))
SIMILARITY_THRESHOLD = float(
    os.getenv("SIMILARITY_THRESHOLD", str(DEFAULT_SIMILARITY_THRESHOLD))
)
LLM_RAG_MODEL = os.getenv("LLM_RAG_MODEL", NIM_MODEL)

# Qwen semantic-normalization runtime configuration
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", DEFAULT_QWEN_BASE_URL).rstrip("/")
QWEN_MODEL = os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL)
QWEN_TIMEOUT_SECONDS = int(
    os.getenv("QWEN_TIMEOUT_SECONDS", str(DEFAULT_QWEN_TIMEOUT_SECONDS))
)
QWEN_MAX_INPUT_CHARS = int(
    os.getenv("QWEN_MAX_INPUT_CHARS", str(DEFAULT_QWEN_MAX_INPUT_CHARS))
)
