"""Phase 13A acquisition tests.

No live-website dependency: a local HTTP server stands in for the official
host, and the allowlist is patched to include it for the duration of a test.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import threading
import time
from pathlib import Path

import pytest

from scripts.acquisition import fetch as fetch_module
from scripts.acquisition import storage
from scripts.acquisition.fetch import (
    ContentTooLargeError,
    DisallowedHostError,
    MimeMismatchError,
    fetch,
)
from scripts.acquisition.sources import (
    APPROVED_API_SOURCES,
    APPROVED_DOCUMENT_SOURCES,
    APPROVED_PAGE_SOURCES,
)


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence test output
        pass

    def do_GET(self):
        if self.path == "/ok-html":
            body = b"<html>hello</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/big":
            body = b"x" * (2 * 1024 * 1024)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/wrong-mime":
            body = b"not a pdf"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/redirect-external":
            self.send_response(302)
            self.send_header("Location", "https://evil.example.com/steal")
            self.end_headers()
        elif self.path == "/redirect-internal":
            self.send_response(302)
            self.send_header("Location", f"http://{self.headers.get('Host')}/ok-html")
            self.end_headers()
        elif self.path == "/slow":
            time.sleep(2.0)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"slow")
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def local_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"{host}:{port}"
    server.shutdown()
    thread.join()


@pytest.fixture
def allow_local_host(local_server, monkeypatch):
    host = local_server.split(":")[0]
    monkeypatch.setattr(fetch_module, "ALLOWED_HOSTS", frozenset({host}))
    return local_server


def test_disallowed_host_rejected():
    with pytest.raises(DisallowedHostError):
        fetch("https://not-an-approved-host.example.com/")


def test_allowed_host_ok(allow_local_host):
    result = fetch(f"http://{allow_local_host}/ok-html", min_request_interval=0.0)
    assert result.http_status == 200
    assert result.content_type == "text/html"
    assert result.body == b"<html>hello</html>"


def test_redirect_outside_allowlist_blocked(allow_local_host):
    with pytest.raises(DisallowedHostError):
        fetch(f"http://{allow_local_host}/redirect-external", min_request_interval=0.0)


def test_redirect_within_allowlist_followed(allow_local_host):
    result = fetch(f"http://{allow_local_host}/redirect-internal", min_request_interval=0.0)
    assert result.http_status == 200
    assert result.body == b"<html>hello</html>"
    assert len(result.redirect_chain) == 1


def test_content_size_limit_enforced(allow_local_host):
    with pytest.raises(ContentTooLargeError):
        fetch(
            f"http://{allow_local_host}/big",
            max_bytes=1024,
            min_request_interval=0.0,
        )


def test_mime_mismatch_rejected(allow_local_host):
    with pytest.raises(MimeMismatchError):
        fetch(
            f"http://{allow_local_host}/wrong-mime",
            expected_content_types=("application/pdf",),
            min_request_interval=0.0,
        )


def test_timeout_raises(allow_local_host):
    with pytest.raises((TimeoutError, OSError)):
        fetch(f"http://{allow_local_host}/slow", timeout=0.2, min_request_interval=0.0)


def test_deterministic_hash(allow_local_host):
    r1 = fetch(f"http://{allow_local_host}/ok-html", min_request_interval=0.0)
    r2 = fetch(f"http://{allow_local_host}/ok-html", min_request_interval=0.0)
    assert r1.sha256 == r2.sha256 == hashlib.sha256(b"<html>hello</html>").hexdigest()


def test_immutable_raw_storage_no_overwrite(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    body = b"content-a"
    sha = hashlib.sha256(body).hexdigest()
    path1, is_new1 = storage.save_raw(raw_dir, sha, "text/html", body)
    assert is_new1 is True
    assert path1.read_bytes() == body

    # Re-saving identical content under the same hash must not rewrite/duplicate.
    path2, is_new2 = storage.save_raw(raw_dir, sha, "text/html", body)
    assert is_new2 is False
    assert path2 == path1


def test_changed_content_gets_new_immutable_file(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    body_v1 = b"version-one"
    body_v2 = b"version-two"
    sha1 = hashlib.sha256(body_v1).hexdigest()
    sha2 = hashlib.sha256(body_v2).hexdigest()

    path1, _ = storage.save_raw(raw_dir, sha1, "text/html", body_v1)
    path2, _ = storage.save_raw(raw_dir, sha2, "text/html", body_v2)

    assert path1 != path2
    assert path1.read_bytes() == body_v1
    assert path2.read_bytes() == body_v2


def test_manifest_append_only(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    entry_a = {
        "source_url": "http://example.test/a",
        "source_type": "HTML_PAGE",
        "retrieval_timestamp": "2026-01-01T00:00:00+00:00",
        "http_status": 200,
        "content_type": "text/html",
        "content_length": 10,
        "sha256": "a" * 64,
        "raw_file": "raw/a.html",
        "is_new_content": True,
    }
    entry_b = dict(entry_a, retrieval_timestamp="2026-01-02T00:00:00+00:00")

    storage.append_manifest_entry(manifest_path, entry_a)
    storage.append_manifest_entry(manifest_path, entry_b)

    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[0]["retrieval_timestamp"] != entries[1]["retrieval_timestamp"]


def test_manifest_entry_validation():
    complete_entry = {
        "source_url": "http://example.test/a",
        "source_type": "HTML_PAGE",
        "retrieval_timestamp": "2026-01-01T00:00:00+00:00",
        "http_status": 200,
        "content_type": "text/html",
        "content_length": 10,
        "sha256": "a" * 64,
        "raw_file": "raw/a.html",
        "is_new_content": True,
    }
    assert storage.validate_manifest_entry(complete_entry) == []

    incomplete_entry = {"source_url": "http://example.test/a"}
    problems = storage.validate_manifest_entry(incomplete_entry)
    assert problems != []


def test_no_normalization_or_identity_generation_helpers_exposed():
    # This module must not offer identity/normalization helpers: acquisition
    # is raw capture only.
    assert not hasattr(storage, "generate_public_id")
    assert not hasattr(storage, "normalize_rarity")
    assert not hasattr(fetch_module, "generate_public_id")


def test_no_artwork_urls_in_approved_source_list():
    all_urls = [
        s.url for s in (*APPROVED_PAGE_SOURCES, *APPROVED_DOCUMENT_SOURCES, *APPROVED_API_SOURCES)
    ]
    assert not any("cards.narutotcgmythos.com/storage/cards" in u for u in all_urls)


def test_approved_sources_are_https_and_allowlisted():
    for source in (*APPROVED_PAGE_SOURCES, *APPROVED_DOCUMENT_SOURCES, *APPROVED_API_SOURCES):
        assert source.url.startswith("https://")
        host = source.url.split("/")[2].split("?")[0]
        assert host in fetch_module.ALLOWED_HOSTS


def test_disallowed_host_error_before_any_network_read():
    # A blocked host must raise without ever depending on live network access.
    with pytest.raises(DisallowedHostError):
        fetch("https://example.invalid.host.test/x")
