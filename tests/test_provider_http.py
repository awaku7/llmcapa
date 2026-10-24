from __future__ import annotations

import importlib.util
from pathlib import Path

from scripts import _scrape_amazon, _update_liquid
from scripts.provider_updates import (
    _http,
    ai21,
    cerebras,
    groq,
    sambanova,
    thinkingmachines,
    writer,
)

ROOT = Path(__file__).resolve().parents[1]


def test_fetch_bytes_passes_headers_timeout_and_read_limit(monkeypatch):
    observed = {}
    body = b"0123456789"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, limit=-1):
            observed["read_limit"] = limit
            return body if limit < 0 else body[:limit]

    def fake_urlopen(request, *, timeout):
        observed["url"] = request.full_url
        observed["accept"] = request.get_header("Accept")
        observed["user_agent"] = request.get_header("User-agent")
        observed["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(_http, "urlopen", fake_urlopen)
    result = _http.fetch_bytes(
        "https://example.test/catalog",
        headers={"Accept": "text/plain", "User-Agent": "test-agent"},
        timeout=7,
        max_bytes=4,
    )

    assert result == b"0123"
    assert observed == {
        "url": "https://example.test/catalog",
        "accept": "text/plain",
        "user_agent": "test-agent",
        "timeout": 7,
        "read_limit": 4,
    }


def test_fetch_text_decodes_with_requested_error_policy(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, _limit=-1):
            return b"caf\xe9"

    monkeypatch.setattr(_http, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    assert _http.fetch_text("https://example.test", encoding="latin-1") == "café"


def test_ai21_fetch_uses_shared_bounded_text_helper(monkeypatch):
    observed = {}
    document = "## Model Details\nAPI Endpoint"

    def fake_fetch_text(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return document

    monkeypatch.setattr(ai21, "fetch_text", fake_fetch_text)
    assert ai21.fetch_docs() == document
    assert observed == {
        "url": ai21.SOURCE + ".md",
        "headers": {
            "Accept": "text/markdown,text/plain,*/*",
            "User-Agent": "llmcapa-provider-updater/1.0",
        },
        "timeout": 30,
        "max_bytes": 1_000_000,
    }


def test_writer_fetch_uses_shared_bounded_text_helper(monkeypatch):
    observed = {}

    def fake_fetch_text(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return "official docs"

    monkeypatch.setattr(writer, "fetch_text", fake_fetch_text)
    assert writer._fetch_markdown(writer.MODELS_SOURCE) == "official docs"
    assert observed == {
        "url": writer.MODELS_SOURCE + ".md",
        "headers": {
            "Accept": "text/markdown,text/plain,*/*",
            "User-Agent": "llmcapa-provider-updater/1.0",
        },
        "timeout": 30,
        "max_bytes": 4_000_000,
    }


def test_amazon_scraper_uses_shared_byte_fetcher(monkeypatch):
    observed = {}

    def fake_fetch_bytes(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return b"compressed or HTML bytes"

    monkeypatch.setattr(_scrape_amazon, "fetch_bytes", fake_fetch_bytes)
    assert (
        _scrape_amazon._fetch(_scrape_amazon.PRICING_URL) == b"compressed or HTML bytes"
    )
    assert observed == {
        "url": _scrape_amazon.PRICING_URL,
        "headers": {"User-Agent": "llmcapa catalog updater"},
        "timeout": 30,
    }


def test_tinker_fetch_uses_shared_bounded_text_helper(monkeypatch):
    observed = {}
    docs = "Tinker ID\n## Training"

    def fake_fetch_text(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return docs

    monkeypatch.setattr(thinkingmachines, "fetch_text", fake_fetch_text)
    assert thinkingmachines.fetch_docs() == docs
    assert observed == {
        "url": thinkingmachines.SOURCE + "/index.md",
        "headers": {
            "Accept": "text/markdown,text/plain,*/*",
            "User-Agent": "llmcapa-provider-updater/1.0",
        },
        "timeout": 30,
        "max_bytes": 5_000_000,
    }


def test_zai_fetch_uses_shared_bounded_text_helper(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "test_zai_provider_http", ROOT / "scripts" / "provider_updates" / "z-ai.py"
    )
    assert spec and spec.loader
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)

    observed = {}
    docs = "## Models\n### Text Models"

    def fake_fetch_text(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return docs

    monkeypatch.setattr(updater, "fetch_text", fake_fetch_text)
    assert updater.fetch_docs() == docs
    assert observed == {
        "url": updater.SOURCE + ".md",
        "headers": {
            "Accept": "text/markdown,text/plain,*/*",
            "User-Agent": "llmcapa-provider-updater/1.0",
        },
        "timeout": 30,
        "max_bytes": 2_000_000,
    }


def test_sambanova_fetch_preserves_ignored_decode_and_lowercase(monkeypatch):
    observed = {}

    def fake_fetch_text(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return "MODEL PAGE"

    monkeypatch.setattr(sambanova, "fetch_text", fake_fetch_text)
    assert sambanova.fetch_page() == "model page"
    assert observed == {
        "url": sambanova.SOURCE,
        "headers": {"User-Agent": "llmcapa-official-updater/1.0"},
        "timeout": 30,
        "max_bytes": 500_000,
        "errors": "ignore",
    }


def test_cerebras_and_groq_share_http_read_but_keep_fallbacks(monkeypatch):
    for updater in (cerebras, groq):
        observed = {}

        def fake_fetch_text(url, **kwargs):
            observed["url"] = url
            observed.update(kwargs)
            return "official model page"

        monkeypatch.setattr(updater, "fetch_text", fake_fetch_text)
        assert updater.fetch() == "official model page"
        assert observed == {
            "url": updater.SOURCE,
            "headers": {"User-Agent": "llmcapa-official-scraper/1.0"},
            "timeout": 60,
            "errors": "ignore",
        }


def test_bytedance_seed_fetch_keeps_large_html_limit_and_error_policy(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "test_bytedance_seed_provider_http",
        ROOT / "scripts" / "provider_updates" / "bytedance-seed.py",
    )
    assert spec and spec.loader
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)

    observed = {}
    page = "模型列表 Model ID doubao-seed-2-1-pro-260915"

    def fake_fetch_text(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return page

    monkeypatch.setattr(updater, "fetch_text", fake_fetch_text)
    assert updater.fetch_inventory() == page
    assert observed == {
        "url": updater.SOURCE,
        "headers": {
            "Accept": "text/html",
            "User-Agent": "Mozilla/5.0 (compatible; llmcapa-provider-updater/1.0)",
        },
        "timeout": 45,
        "max_bytes": 12_000_000,
    }


def test_liquid_wrapper_delegates_transport_and_preserves_limit(monkeypatch):
    observed = {}

    def fake_fetch_text(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return "liquid docs"

    monkeypatch.setattr(_update_liquid, "_shared_fetch_text", fake_fetch_text)
    assert (
        _update_liquid.fetch_text("https://example.test/page", limit=1234)
        == "liquid docs"
    )
    assert observed == {
        "url": "https://example.test/page",
        "headers": {
            "Accept": "text/markdown,text/plain,*/*",
            "User-Agent": "llmcapa-provider-updater/1.0",
        },
        "timeout": 30,
        "max_bytes": 1234,
    }
