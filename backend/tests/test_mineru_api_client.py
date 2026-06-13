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
        return httpx.Response(200, json={"status": "healthy", "version": "3.3.1"})

    client = MineruApiClient(
        base_url="http://mineru-router:8002",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.health()

    assert result["available"] is True
    assert result["base_url"] == "http://mineru-router:8002"
    assert result["status"] == "healthy"
    assert result["version"] == "3.3.1"


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
        assert b'name="return_images"\r\n\r\ntrue' in body
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


def test_parse_file_includes_hybrid_effort_for_mineru_3_3():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'name="effort"\r\n\r\nhigh' in body
        return httpx.Response(
            200,
            content=make_zip_bytes(),
            headers={"content-type": "application/zip"},
        )

    client = MineruApiClient(
        base_url="http://mineru-router:8002",
        hybrid_effort="high",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.parse_file(
        filename="sample.pdf",
        file_bytes=b"%PDF",
        backend="hybrid-engine",
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


def test_async_parse_reports_task_progress_callback():
    calls = []
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        if request.url.path == "/tasks" and request.method == "POST":
            return httpx.Response(200, json={"task_id": "task-123"})
        if request.url.path == "/tasks/task-123":
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(200, json={"status": "running", "progress": 48, "message": "layout"})
            return httpx.Response(200, json={"status": "success", "progress": 100, "message": "done"})
        if request.url.path == "/tasks/task-123/result":
            return httpx.Response(
                200,
                content=make_zip_bytes(),
                headers={"content-type": "application/zip"},
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    client = MineruApiClient(
        base_url="http://mineru-router:8002",
        use_async_tasks=True,
        poll_interval_seconds=0,
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
        progress_callback=calls.append,
    )

    assert result.content.startswith(b"PK")
    assert calls == [
        {"task_id": "task-123", "status": "submitted", "payload": {"task_id": "task-123"}},
        {
            "task_id": "task-123",
            "status": "running",
            "payload": {"status": "running", "progress": 48, "message": "layout"},
        },
        {
            "task_id": "task-123",
            "status": "success",
            "stage": "downloading_result",
            "message": "正在下载解析结果",
            "payload": {"status": "success", "progress": 100, "message": "done"},
        },
    ]
