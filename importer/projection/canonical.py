"""Versioned deterministic JSON hashing without I/O."""

import hashlib
import json
import unicodedata


def encode(value) -> str:
    """Normalize strings/keys to NFC; reject key collisions and non-finite numbers."""

    def normalize(item):
        if isinstance(item, str):
            return unicodedata.normalize("NFC", item)
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                if not isinstance(key, str):
                    raise TypeError("Canonical objects require string keys")
                key = normalize(key)
                if key in result:
                    raise ValueError("Duplicate normalized key")
                result[key] = normalize(child)
            return result
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if item is None or type(item) in (bool, int, float):
            return item
        raise ValueError("Unsupported canonical value")

    return json.dumps(
        normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value) -> str:
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()
