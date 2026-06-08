import io
import zipfile

import httpx
import pytest

from app.services.mineru_api import MineruApiClient, MineruApiError


def make_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("sample/sample.md", "![](images/a.png)")
        zf.writestr("sample/images/a.png", b"png")
    return buffer.getvalue()


def test_health_returns_normalized_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "healthy", "version": "3.2.3"})

    client = MineruApiClient(
        base_url="http://mineru-router:8002",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.health()

    assert result["available"] is True
    assert result["base_url"] == "http://mineru-router:8002"
    assert result["status"] == "healthy"
    assert result["version"] == "3.2.3"


def test_health_handles_unavailable_service():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = MineruApiClient(
        base_url="http://mineru-router:8002",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.health()

    assert result["available"] is False
    assert "refused" in result["error"]


def test_parse_file_posts_zip_request_and_returns_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/file_parse"
        body = request.read()
        assert b'name="files"; filename="sample.pdf"' in body
        assert b'name="lang_list"' in body
        assert b"response_format_zip" in body
        assert b"return_md" in body
        return httpx.Response(
            200,
            content=make_zip_bytes(),
            headers={"content-type": "application/zip"},
        )

    client = MineruApiClient(
        base_url="http://mineru-router:8002",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.parse_file(
        filename="sample.pdf",
        file_bytes=b"%PDF",
        backend="pipeline",
        parse_method="auto",
        lang="ch",
        formula_enable=True,
        table_enable=True,
    )

    assert result.filename == "sample.pdf"
    assert result.content_type == "application/zip"
    assert result.content.startswith(b"PK")


def test_parse_file_includes_server_url_when_configured():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b"server_url" in body
        assert b"http://openai-compatible-server:30000" in body
        return httpx.Response(
            200,
            content=make_zip_bytes(),
            headers={"content-type": "application/zip"},
        )

    client = MineruApiClient(
        base_url="http://mineru-router:8002",
        server_url="http://openai-compatible-server:30000",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.parse_file(
        filename="sample.pdf",
        file_bytes=b"%PDF",
        backend="hybrid-http-client",
        parse_method="auto",
        lang="ch",
        formula_enable=True,
        table_enable=True,
    )


def test_parse_file_raises_on_non_success_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = MineruApiClient(
        base_url="http://mineru-router:8002",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(MineruApiError) as exc:
        client.parse_file(
            filename="sample.pdf",
            file_bytes=b"%PDF",
            backend="pipeline",
            parse_method="auto",
            lang="ch",
            formula_enable=True,
            table_enable=True,
        )

    assert "boom" in str(exc.value)
