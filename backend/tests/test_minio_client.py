from datetime import timedelta

from app.utils import minio_client as minio_module


class FakeMinio:
    def __init__(self, endpoint, access_key=None, secret_key=None, secure=False, region=None):
        self.endpoint = endpoint
        self.secure = secure
        self.region = region

    def presigned_get_object(self, bucket, path, expires=None):
        assert expires == timedelta(seconds=600)
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self.endpoint}/{bucket}/{path}?signed=1"


def test_get_presigned_url_uses_configured_endpoint_for_browser(monkeypatch):
    monkeypatch.setattr(minio_module, "Minio", FakeMinio)
    monkeypatch.setattr(minio_module, "minio_client", FakeMinio("localhost:9000"))

    url = minio_module.get_presigned_url("mineru-files", "sample.pdf", expires=600)

    assert url == "http://localhost:9000/mineru-files/sample.pdf?signed=1"
