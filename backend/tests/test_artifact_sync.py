import io
import zipfile

from app.services.artifact_sync import MineruArtifactSync


class FakeMinioClient:
    def __init__(self):
        self.objects = {}
        self.buckets = set()

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets.add(bucket)

    def put_object(self, bucket, path, data, length, content_type=None):
        self.buckets.add(bucket)
        self.objects[(bucket, path)] = data.read()


def build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("sample/sample.md", "# Title\n\n![](images/a.png)")
        zf.writestr("sample/sample_middle.json", '{"pdf_info": []}')
        zf.writestr("sample/images/a.png", b"PNG")
    return buffer.getvalue()


def test_sync_zip_uploads_markdown_images_and_rewrites_urls():
    client = FakeMinioClient()
    sync = MineruArtifactSync(
        minio=client,
        bucket="mds",
        endpoint="http://minio:9000",
        public_endpoint="http://localhost:9000",
    )

    result = sync.sync_zip(build_zip(), output_name="sample")

    assert result.markdown == "# Title\n\n![](http://localhost:9000/mds/sample/images/a.png)"
    assert client.objects[("mds", "sample/sample.md")] == result.markdown.encode("utf-8")
    assert client.objects[("mds", "sample/images/a.png")] == b"PNG"
    assert client.objects[("mds", "sample/sample_middle.json")] == b'{"pdf_info": []}'


def test_sync_zip_raises_when_markdown_missing():
    client = FakeMinioClient()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("sample/images/a.png", b"PNG")

    sync = MineruArtifactSync(minio=client, bucket="mds", endpoint="http://minio:9000")

    try:
        sync.sync_zip(buffer.getvalue(), output_name="sample")
    except ValueError as exc:
        assert "Markdown artifact not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")
