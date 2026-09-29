"""Delete all documents through the unauthenticated local API."""

import os

import requests


BASE_URL = os.getenv("RAG_BASE_URL", "http://localhost:41873")


def main() -> int:
    """Delete all stored documents and print the API response."""
    response = requests.delete(f"{BASE_URL}/api/documents/bulk/all?filter=all", timeout=30)
    response.raise_for_status()
    print(response.json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
