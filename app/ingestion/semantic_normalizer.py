"""Provider router for OCR correction and semantic normalization.

Policy ``auto`` intentionally prefers the already-running local Qwen endpoint.
The hosted NVIDIA endpoint is a failover, not a hard dependency.
"""

from __future__ import annotations

import time

from app.config.settings import NGC_API_KEY, NIM_MODEL, SEMANTIC_NORMALIZER


def _providers(policy: str) -> list[str]:
    policy = (policy or "none").strip().lower()
    if policy in {"none", "off", "false"}:
        return []
    if policy in {"local", "qwen", "local_qwen"}:
        return ["local_qwen"]
    if policy in {"nim", "nvidia", "nvidia_nim"}:
        return ["nvidia_nim"]
    if policy == "auto":
        return ["local_qwen", "nvidia_nim"] if NGC_API_KEY else ["local_qwen"]
    raise ValueError(
        "SEMANTIC_NORMALIZER must be one of auto, local, nvidia, or none"
    )


def normalize_document(
    clean_text: str,
    source_elements: list[dict],
    *,
    policy: str = SEMANTIC_NORMALIZER,
    progress_callback=None,
) -> tuple[dict | None, str | None, dict]:
    """Normalize document."""
    providers = _providers(policy)
    if not providers:
        return None, None, {"provider": "none", "status": "skipped"}

    errors: list[str] = []
    for provider in providers:
        started = time.monotonic()
        if provider == "local_qwen":
            from app.ingestion.qwen_normalizer import QWEN_MODEL, normalize

            result, error = normalize(clean_text, source_elements)
            model = QWEN_MODEL
            if progress_callback:
                progress_callback(1, 1)
        else:
            from app.ingestion.nim_normalizer import normalize_parallel

            result, error = normalize_parallel(
                clean_text,
                source_elements,
                progress_callback=progress_callback,
            )
            model = NIM_MODEL

        elapsed = round(time.monotonic() - started, 3)
        if result and not error and result.get("elements"):
            result["provider"] = provider
            result["model"] = model
            result["elapsed_seconds"] = elapsed
            return result, None, {
                "provider": provider,
                "model": model,
                "status": "processed",
                "elapsed_seconds": elapsed,
                "attempt_errors": errors,
            }
        errors.append(f"{provider}: {error or 'empty result'}")

    message = "; ".join(errors)
    return None, message, {
        "provider": "rule_based",
        "status": "fallback_rule_based",
        "error": message,
        "attempt_errors": errors,
    }
