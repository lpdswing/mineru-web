import json
from types import SimpleNamespace
from fastapi.testclient import TestClient

from app.database import get_db
from app.api.parsed import _normalize_source_map
from app.models.file import File as FileModel
from app.models.parsed_content import ParsedContent
from main import app


class FakeObject:
    def __init__(self, content):
        self.content = content
        self.closed = False
        self.released = False

    def read(self):
        return self.content

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


class FakeQuery:
    def __init__(self, item):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item


class FakeDb:
    def __init__(self, file, parsed_content=None):
        self.file = file
        self.parsed_content = parsed_content

    def query(self, model):
        if model is FileModel:
            return FakeQuery(self.file)
        if model is ParsedContent:
            return FakeQuery(self.parsed_content)
        return FakeQuery(None)


class FakeMinio:
    def __init__(self):
        self.stat_calls = []
        self.get_calls = []
        self.get_responses = []
        self.objects = {}
        self.existing_objects = {
            ("mds", "sample.md"): b"# Main",
            ("mds", "sample_pages.md"): b"# Pages",
            ("mds", "sample_popo.md"): b"# Popo",
            ("mds", "sample_popo_status.json"): b'{"status":"success","message":""}',
        }

    def stat_object(self, bucket, path):
        self.stat_calls.append((bucket, path))
        if (bucket, path) not in self.existing_objects and (bucket, path) not in self.objects:
            raise FileNotFoundError(path)

    def put_object(self, bucket, path, data, length, content_type=None):
        self.objects[(bucket, path)] = {
            "content": data.read(),
            "content_type": content_type,
        }

    def get_object(self, bucket, path):
        self.get_calls.append((bucket, path))
        if (bucket, path) in self.objects:
            response = FakeObject(self.objects[(bucket, path)]["content"])
            self.get_responses.append(response)
            return response
        if (bucket, path) in self.existing_objects:
            response = FakeObject(self.existing_objects[(bucket, path)])
            self.get_responses.append(response)
            return response
        raise FileNotFoundError(path)


class MissingMinio(FakeMinio):
    def stat_object(self, bucket, path):
        self.stat_calls.append((bucket, path))
        raise FileNotFoundError(path)


class FailingStatMinio(FakeMinio):
    def stat_object(self, bucket, path):
        self.stat_calls.append((bucket, path))
        raise RuntimeError("minio down")


class FakeS3Error(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class MissingGetS3Minio(FakeMinio):
    def get_object(self, bucket, path):
        self.get_calls.append((bucket, path))
        raise FakeS3Error("NoSuchKey")


def test_export_endpoint_returns_main_markdown_download_url(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="原文件.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample.md")]
    assert response.json() == {
        "status": "success",
        "download_url": "http://minio/mds/sample.md?signed=1",
        "filename": "原文件.md",
    }


def test_export_endpoint_returns_page_markdown_download_url(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_page"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample_pages.md")]
    assert response.json()["download_url"] == "http://minio/mds/sample_pages.md?signed=1"
    assert response.json()["filename"] == "sample_pages.md"


def test_export_endpoint_repairs_missing_main_markdown_from_database(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_content = SimpleNamespace(content="# Parsed")
    fake_minio = MissingMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file, parsed_content=fake_content)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample.md")]
    assert fake_minio.objects[("mds", "sample.md")] == {
        "content": b"# Parsed",
        "content_type": "text/markdown; charset=utf-8",
    }
    assert response.json()["download_url"] == "http://minio/mds/sample.md?signed=1"


def test_export_endpoint_returns_404_when_page_markdown_artifact_missing(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = MissingMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_page"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert fake_minio.stat_calls == [("mds", "sample_pages.md")]


def test_export_endpoint_returns_500_when_minio_stat_fails(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FailingStatMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_page"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "minio down"
    assert fake_minio.stat_calls == [("mds", "sample_pages.md")]


def test_parsed_content_returns_popo_markdown(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/parsed_content",
            params={"variant": "popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == "# Popo"
    assert fake_minio.get_responses[0].closed is True
    assert fake_minio.get_responses[0].released is True


def test_parsed_content_returns_404_when_minio_get_reports_missing_s3_error(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = MissingGetS3Minio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.S3Error", FakeS3Error)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/parsed_content",
            params={"variant": "popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert fake_minio.get_calls == [("mds", "sample_popo.md")]


def test_parsed_content_rejects_markdown_popo_variant(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)

    try:
        response = TestClient(app).get(
            "/api/files/3/parsed_content",
            params={"variant": "markdown_popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_export_endpoint_returns_popo_markdown_download_url(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample_popo.md")]
    assert response.json()["download_url"] == "http://minio/mds/sample_popo.md?signed=1"
    assert response.json()["filename"] == "sample_popo.md"


def test_export_endpoint_rejects_popo_format(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_popo_status_returns_status_json(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/popo/status",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": ""}
    assert fake_minio.get_responses[0].closed is True
    assert fake_minio.get_responses[0].released is True


def test_popo_status_returns_not_available_when_artifact_missing(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()
    del fake_minio.existing_objects[("mds", "sample_popo_status.json")]

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/popo/status",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "not_available", "message": ""}


def test_popo_status_returns_not_available_when_minio_get_reports_missing_s3_error(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = MissingGetS3Minio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.S3Error", FakeS3Error)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/popo/status",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "not_available", "message": ""}
    assert fake_minio.get_calls == [("mds", "sample_popo_status.json")]


def test_popo_status_returns_500_when_status_json_is_corrupt(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()
    fake_minio.existing_objects[("mds", "sample_popo_status.json")] = b"{"

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/popo/status",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500


def test_source_map_returns_blocks_from_nested_middle_json(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()
    fake_minio.existing_objects[("mds", "sample/auto/sample_middle.json")] = json.dumps(
        {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "page_size": [600, 800],
                    "para_blocks": [
                        {
                            "type": "text",
                            "bbox": [10, 20, 200, 60],
                            "lines": [{"spans": [{"content": "Hello MinerU"}]}],
                        },
                        {
                            "type": "table",
                            "poly": [30, 40, 180, 40, 180, 90, 30, 90],
                            "text": "A1",
                        },
                        {
                            "type": "image",
                            "bbox": [40, 100, 220, 180],
                            "blocks": [
                                {
                                    "type": "image_caption",
                                    "bbox": [45, 185, 215, 205],
                                    "lines": [{"spans": [{"content": "A caption from a documented nested block"}]}],
                                }
                            ],
                        },
                    ],
                },
                {
                    "page_idx": 2,
                    "width": 610,
                    "height": 810,
                    "layout_dets": [
                        {
                            "category_type": "title",
                            "bbox": [15, 25, 210, 75],
                            "text": "Third page",
                        }
                    ],
                },
            ]
        }
    ).encode("utf-8")

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/source_map",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.get_calls == [
        ("mds", "sample/sample_middle.json"),
        ("mds", "sample/auto/sample_middle.json"),
    ]
    assert response.json() == {
        "pages": [
            {
                "page": 1,
                "page_idx": 0,
                "width": 600,
                "height": 800,
                "blocks": [
                    {
                        "id": "p1-b1",
                        "type": "text",
                        "text": "Hello MinerU",
                        "bbox": [10, 20, 200, 60],
                    },
                    {
                        "id": "p1-b2",
                        "type": "table",
                        "text": "A1",
                        "bbox": [30, 40, 180, 90],
                    },
                    {
                        "id": "p1-b3",
                        "type": "image",
                        "text": "A caption from a documented nested block",
                        "bbox": [40, 100, 220, 180],
                    },
                ],
            },
            {
                "page": 3,
                "page_idx": 2,
                "width": 610,
                "height": 810,
                "blocks": [
                    {
                        "id": "p3-b1",
                        "type": "title",
                        "text": "Third page",
                        "bbox": [15, 25, 210, 75],
                    }
                ],
            },
        ]
    }


def test_source_map_keeps_longest_text_for_duplicate_bbox():
    result = _normalize_source_map(
        {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "page_size": [600, 800],
                    "para_blocks": [
                        {
                            "type": "text",
                            "bbox": [84, 746, 528, 761],
                            "text": "As depicted in Figure 3, the thinking time improves-",
                        },
                        {
                            "type": "text",
                            "bbox": [84, 746, 528, 761],
                            "text": "As depicted in Figure 3, the thinking time improves throughout training.",
                        },
                    ],
                }
            ]
        }
    )

    assert result["pages"][0]["blocks"] == [
        {
            "id": "p1-b1",
            "type": "text",
            "text": "As depicted in Figure 3, the thinking time improves throughout training.",
            "bbox": [84, 746, 528, 761],
        }
    ]


def test_source_map_returns_empty_pages_when_middle_json_missing(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/source_map",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.get_calls == [
        ("mds", "sample/sample_middle.json"),
        ("mds", "sample/auto/sample_middle.json"),
        ("mds", "sample_middle.json"),
    ]
    assert response.json() == {"pages": []}
