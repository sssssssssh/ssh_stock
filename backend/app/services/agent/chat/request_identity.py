from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid

REQUEST_CONTRACT_VERSION = "m16.2.1-request-v1"


def normalize_request_content(content: str) -> str:
    """Canonicalize text without collapsing meaningful internal whitespace."""
    normalized = unicodedata.normalize("NFKC", content)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.strip().split("\n"))


def request_content_hash(
    *,
    content: str,
    chat_id: uuid.UUID,
    owner_id: uuid.UUID,
    contract_version: str = REQUEST_CONTRACT_VERSION,
) -> str:
    payload = {
        "chat_id": str(chat_id),
        "content": normalize_request_content(content),
        "contract_version": contract_version,
        "owner_id": str(owner_id),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
