"""Semantic SHA-256 with stable UTF-8 JSON, including explicit nulls."""

import hashlib
import json
from datetime import date, datetime


def canonical_hash(data: dict) -> str:
    def encode(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        raise TypeError("Unsupported semantic hash value")

    canonical = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=encode,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
