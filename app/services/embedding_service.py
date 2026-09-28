"""
Embedding Service
=================
Tạo vector embedding cho tài liệu và câu hỏi truy vấn.
Sử dụng NVIDIA NIM Embedding API (model nvidia/nv-embedqa-e5-v5 hoặc baai/bge-m3).
"""

import os
import time
import json
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional

from app.core.config import (
    NGC_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
)

logger = logging.getLogger("embedding_service")


class EmbeddingService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fallback_to_mock: bool = False,
    ):
        self.api_key = (api_key or NGC_API_KEY or "").strip()
        self.base_url = (base_url or EMBEDDING_BASE_URL or "https://integrate.api.nvidia.com/v1").rstrip("/")
        self.model = model or EMBEDDING_MODEL or "nvidia/nv-embedqa-e5-v5"
        self.fallback_to_mock = fallback_to_mock

    def embed_texts(self, texts: List[str], input_type: str = "passage") -> List[List[float]]:
        """
        Embed một danh sách các đoạn văn bản (batch).
        input_type: "passage" (cho chunks văn bản) hoặc "query" (cho câu hỏi tìm kiếm).
        """
        if not texts:
            return []

        if not self.api_key:
            if not self.fallback_to_mock:
                raise RuntimeError("NGC_API_KEY is required when mock embedding fallback is disabled")
            logger.warning("NGC_API_KEY không được cấu hình. Sử dụng mock embedding cho testing.")
            return [self._mock_embedding(t) for t in texts]

        # Batching để tránh vượt quá payload limit (tối đa 32 texts / request)
        batch_size = 16
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = self._call_embedding_api(batch, input_type=input_type)
            all_embeddings.extend(batch_embeddings)

        if len(all_embeddings) != len(texts):
            raise RuntimeError(
                f"Embedding API returned {len(all_embeddings)} vectors for {len(texts)} inputs"
            )
        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """Embed một câu hỏi truy vấn (dùng input_type='query' để tối ưu retrieval)."""
        results = self.embed_texts([query], input_type="query")
        return results[0] if results else [0.0] * EMBEDDING_DIM

    def _call_embedding_api(self, texts: List[str], input_type: str = "passage") -> List[List[float]]:
        endpoint = f"{self.base_url}/embeddings"
        
        # Làm sạch các đoạn text
        cleaned_inputs = [t.strip() if t.strip() else " " for t in texts]

        payload = {
            "model": self.model,
            "input": cleaned_inputs,
            "encoding_format": "float",
        }
        # nv-embedqa hỗ trợ tham số input_type
        if "nv-embedqa" in self.model:
            payload["input_type"] = input_type

        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "MiniRAG-EmbeddingService/1.0",
        }

        max_retries = 3
        backoff = 1.5

        for attempt in range(max_retries):
            req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    resp_body = json.loads(resp.read().decode("utf-8"))
                    data_items = resp_body.get("data", [])
                    # Sắp xếp theo index nếu có
                    data_items.sort(key=lambda x: x.get("index", 0))
                    embeddings = [item["embedding"] for item in data_items]
                    return embeddings
            except urllib.error.HTTPError as http_err:
                err_content = http_err.read().decode("utf-8", errors="ignore")
                logger.warning(
                    "Embedding API HTTP %d (attempt %d/%d): %s",
                    http_err.code, attempt + 1, max_retries, err_content[:200]
                )
                if http_err.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                logger.error("Embedding API thất bại: %s", err_content[:300])
                if self.fallback_to_mock:
                    return [self._mock_embedding(t) for t in texts]
                raise RuntimeError(f"Embedding API failed with HTTP {http_err.code}: {err_content[:300]}") from http_err
            except Exception as exc:
                logger.warning("Lỗi kết nối Embedding API (attempt %d/%d): %s", attempt + 1, max_retries, exc)
                if attempt < max_retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                if self.fallback_to_mock:
                    return [self._mock_embedding(t) for t in texts]
                raise RuntimeError(f"Embedding API request failed after {max_retries} attempts: {exc}") from exc

        if self.fallback_to_mock:
            return [self._mock_embedding(t) for t in texts]
        raise RuntimeError("Embedding API failed without returning vectors")

    def _mock_embedding(self, text: str) -> List[float]:
        """Tạo deterministic pseudo-embedding phục vụ fallback / offline testing."""
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Trải 32 bytes của SHA256 thành vector 1024 floats chuẩn hóa
        vec = []
        for i in range(EMBEDDING_DIM):
            byte_val = h[i % len(h)]
            vec.append((byte_val / 255.0) - 0.5)
        # Chuẩn hóa L2 norm
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [round(x / norm, 6) for x in vec]
