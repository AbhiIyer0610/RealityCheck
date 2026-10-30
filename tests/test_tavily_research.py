from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.ingestion.text_extractor import TextExtractor
from app.jobs.manager import JobManager
from app.main import create_app


def _build_app(tmp_path: Path, tavily_key: str | None = None):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        analysis_provider="offline",
        tavily_api_key=SecretStr(tavily_key) if tavily_key else None,
        frontend_origin="http://localhost:5173",
    )

    def manager_factory(config: Settings) -> JobManager:
        return JobManager(config, extractors={"text/plain": TextExtractor()})

    return create_app(settings_override=settings, manager_factory=manager_factory)


def test_tavily_search_requires_api_key(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/research/tavily/search", json={"query": "official HTTP 413 documentation"})
    assert response.status_code == 503
    assert "TAVILY_API_KEY" in response.json()["detail"]


def test_tavily_search_returns_curated_public_references(tmp_path: Path, monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{
                "title": "HTTP 413 Content Too Large",
                "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/413",
                "content": "The request content was larger than limits defined by server.",
                "score": 0.91,
                "raw_content": "must not be returned",
            }]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, json, headers):
            assert url == "https://api.tavily.com/search"
            assert json["query"] == "official HTTP 413 documentation"
            assert json["max_results"] == 5
            assert "raw_content" not in json
            assert headers["Authorization"] == "Bearer test-key"
            return FakeResponse()

    monkeypatch.setattr("app.api.routes.httpx.AsyncClient", FakeAsyncClient)
    app = _build_app(tmp_path, "test-key")
    with TestClient(app) as client:
        response = client.post("/api/v1/research/tavily/search", json={
            "query": "official HTTP 413 documentation",
            "include_domains": ["developer.mozilla.org"],
        })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["results"][0]["title"] == "HTTP 413 Content Too Large"
    assert payload["results"][0]["score"] == 0.91
    assert "raw_content" not in payload["results"][0]
    assert "not proof of internal runtime behavior" in payload["note"]


def test_tavily_search_rejects_blank_query(tmp_path: Path) -> None:
    app = _build_app(tmp_path, "test-key")
    with TestClient(app) as client:
        response = client.post("/api/v1/research/tavily/search", json={"query": "   "})
    assert response.status_code == 422
