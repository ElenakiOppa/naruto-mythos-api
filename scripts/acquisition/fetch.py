"""Bounded, allowlisted HTTP fetch for read-only Phase 13A source acquisition.

This module intentionally has no knowledge of card data, rarities, sets or
identity. It only retrieves bytes from pre-approved official hosts and
records factual retrieval metadata (status, content type/length, SHA-256).
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

# Official domain plus first-party CDN hosts directly linked by official pages
# (card image storage subdomain and the site-builder document/asset CDN used
# for collection guide PDFs and the rulebook PDF).
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "narutotcgmythos.com",
        "www.narutotcgmythos.com",
        "cards.narutotcgmythos.com",
        "irp.cdn-website.com",
    }
)

USER_AGENT = (
    "naruto-mythos-api-phase13a-acquisition/1.0 "
    "(read-only research; official public sources only; "
    "contact: repository owner)"
)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB ceiling; guide PDFs/HTML are small
MIN_REQUEST_INTERVAL_SECONDS = 1.0
MAX_RETRIES = 2
RETRYABLE_STATUS_CODES = frozenset({500, 502, 503, 504})


class AcquisitionError(Exception):
    """Base error for acquisition failures."""


class DisallowedHostError(AcquisitionError):
    """Raised when a URL (including a redirect target) is outside the allowlist."""


class ContentTooLargeError(AcquisitionError):
    """Raised when a response body exceeds the configured byte ceiling."""


class MimeMismatchError(AcquisitionError):
    """Raised when the response content-type does not match an expected set."""


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    http_status: int
    content_type: str | None
    content_length: int | None
    body: bytes
    sha256: str
    retrieved_at: str
    redirect_chain: tuple[str, ...]


def _check_host_allowed(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise DisallowedHostError(f"host not in allowlist: {host!r} (url={url!r})")


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that enforces the allowlist on every hop before following it."""

    def __init__(self) -> None:
        super().__init__()
        self.chain: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _check_host_allowed(newurl)
        self.chain.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_last_request_monotonic: float = 0.0


def _rate_limit(min_interval: float) -> None:
    global _last_request_monotonic
    now = time.monotonic()
    elapsed = now - _last_request_monotonic
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_request_monotonic = time.monotonic()


def _read_bounded(response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    chunk_size = 65536
    while True:
        chunk = response.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ContentTooLargeError(f"response body exceeded {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    expected_content_types: tuple[str, ...] | None = None,
    min_request_interval: float = MIN_REQUEST_INTERVAL_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> FetchResult:
    """Fetch one URL from an allowlisted official host.

    Redirect targets are allowlist-checked before being followed. The response
    body is size-bounded. Retries only apply to safe transient (5xx) failures.
    """
    _check_host_allowed(url)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        _rate_limit(min_request_interval)
        handler = _AllowlistRedirectHandler()
        opener = urllib.request.build_opener(handler)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with opener.open(request, timeout=timeout) as response:
                body = _read_bounded(response, max_bytes)
                status = getattr(response, "status", None) or response.getcode()
                content_type = response.headers.get("Content-Type")
                content_length_header = response.headers.get("Content-Length")
                final_url = response.geturl()
        except urllib.error.HTTPError as exc:
            if exc.code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                last_error = exc
                continue
            status = exc.code
            content_type = exc.headers.get("Content-Type") if exc.headers else None
            body = b""
            content_length_header = None
            final_url = exc.geturl() if hasattr(exc, "geturl") else url
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < max_retries:
                last_error = exc
                continue
            raise

        if expected_content_types is not None and content_type is not None:
            normalized = content_type.split(";", 1)[0].strip().lower()
            if normalized not in expected_content_types:
                raise MimeMismatchError(
                    f"unexpected content-type {content_type!r} for {url!r}; "
                    f"expected one of {expected_content_types!r}"
                )

        digest = hashlib.sha256(body).hexdigest()
        content_length = int(content_length_header) if content_length_header else len(body)
        return FetchResult(
            requested_url=url,
            final_url=final_url,
            http_status=int(status),
            content_type=content_type,
            content_length=content_length,
            body=body,
            sha256=digest,
            retrieved_at=datetime.now(UTC).isoformat(),
            redirect_chain=tuple(handler.chain),
        )

    assert last_error is not None
    raise last_error
