from types import SimpleNamespace

from app.pipeline import parse_minio_endpoint
from app.pipeline import PopoPipeline
from app.pipeline import render_popo_markdown


def test_parse_minio_endpoint_keeps_bare_host_port():
    assert parse_minio_endpoint("minio:9000") == ("minio:9000", False)


def test_parse_minio_endpoint_supports_http_urls():
    assert parse_minio_endpoint("http://minio:9000") == ("minio:9000", False)
    assert parse_minio_endpoint("https://minio.example.com") == ("minio.example.com", True)


def test_run_omits_model_json_from_upstream_mineru_input(tmp_path):
    pipeline = PopoPipeline.__new__(PopoPipeline)
    pipeline.workspace = tmp_path
    pipeline.repo_dir = tmp_path / "repo"
    pipeline.model_path = "/models/MinerU-Popo"

    downloaded = []

    def write_status(bucket, object_name, status, message):
        return None

    def download_artifact(bucket, object_name, destination):
        downloaded.append(object_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}", encoding="utf-8")

    def run_popo_commands(job_dir, doc_id):
        vlm_dir = job_dir / "post-process" / "mineru" / doc_id / "vlm"
        assert (vlm_dir / f"{doc_id}_middle.json").exists()
        assert (vlm_dir / f"{doc_id}_content_list.json").exists()
        assert not (vlm_dir / f"{doc_id}_model.json").exists()

        json_dir = job_dir / "outputs" / "build_tree" / "mineru"
        json_dir.mkdir(parents=True, exist_ok=True)
        (json_dir / f"{doc_id}.json").write_text(
            '{"type":"root","children":[{"type":"text","title":"Default Title","content":"full content"}]}',
            encoding="utf-8",
        )

    uploaded = {}

    def upload_file(bucket, object_name, source, content_type):
        uploaded[object_name] = source.read_text(encoding="utf-8")

    pipeline.write_status = write_status
    pipeline.download_artifact = download_artifact
    pipeline.run_popo_commands = run_popo_commands
    pipeline.upload_file = upload_file

    request = SimpleNamespace(
        bucket="mds",
        prefix="doc",
        artifacts={
            "middle_json": "doc/auto/doc_middle.json",
            "content_list_json": "doc/auto/doc_content_list.json",
            "model_json": "doc/auto/doc_model.json",
            "source_pdf": "doc.pdf",
        },
        outputs={
            "status": "doc_popo_status.json",
            "json": "doc_popo.json",
            "markdown": "doc_popo.md",
        },
    )

    pipeline.run(request)

    assert downloaded == [
        "doc/auto/doc_middle.json",
        "doc/auto/doc_content_list.json",
        "doc.pdf",
    ]
    assert uploaded["doc_popo.md"] == "full content\n"


def test_run_downloads_source_pdf_for_upstream_inference(tmp_path):
    pipeline = PopoPipeline.__new__(PopoPipeline)
    pipeline.workspace = tmp_path
    pipeline.repo_dir = tmp_path / "repo"
    pipeline.model_path = "/models/MinerU-Popo"

    downloaded = []

    def write_status(bucket, object_name, status, message):
        return None

    def download_artifact(bucket, object_name, destination):
        downloaded.append((object_name, destination.name))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}", encoding="utf-8")

    def run_popo_commands(job_dir, doc_id):
        source_pdf = job_dir / "source" / f"{doc_id}.pdf"
        pdf_map = job_dir / "pdf-map.json"
        assert source_pdf.exists()
        assert pdf_map.exists()
        json_dir = job_dir / "outputs" / "build_tree" / "mineru"
        json_dir.mkdir(parents=True, exist_ok=True)
        (json_dir / f"{doc_id}.json").write_text('{"type":"root"}', encoding="utf-8")

    def upload_file(bucket, object_name, source, content_type):
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("content", encoding="utf-8")

    pipeline.write_status = write_status
    pipeline.download_artifact = download_artifact
    pipeline.run_popo_commands = run_popo_commands
    pipeline.upload_file = upload_file

    request = SimpleNamespace(
        bucket="mds",
        prefix="doc",
        artifacts={
            "middle_json": "doc/auto/doc_middle.json",
            "content_list_json": "doc/auto/doc_content_list.json",
            "model_json": "doc/auto/doc_model.json",
            "source_pdf": "doc.pdf",
        },
        outputs={
            "status": "doc_popo_status.json",
            "json": "doc_popo.json",
            "markdown": "doc_popo.md",
        },
    )

    pipeline.run(request)

    assert ("doc.pdf", "doc.pdf") in downloaded


def test_render_popo_markdown_uses_full_json_tree_content(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        """
        {
          "type": "root",
          "children": [
            {
              "type": "text",
              "title": "Default Title",
              "content": "第一段完整内容<|txt_split|>第二段<|txt_contd|>继续",
              "children": []
            },
            {
              "type": "text",
              "title": "章节标题",
              "level": 2,
              "content": "标题下的内容",
              "children": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    render_popo_markdown(tree_path, markdown_path)

    assert markdown_path.read_text(encoding="utf-8") == (
        "第一段完整内容\n\n"
        "第二段继续\n\n"
        "## 章节标题\n\n"
        "标题下的内容\n"
    )


def test_stage_artifact_copies_from_local_artifact_root_before_minio(tmp_path):
    artifact_root = tmp_path / "artifact-root"
    source = artifact_root / "doc" / "auto" / "doc_middle.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"from":"local"}', encoding="utf-8")

    pipeline = PopoPipeline.__new__(PopoPipeline)
    pipeline.artifact_root = artifact_root.resolve()

    def download_artifact(bucket, object_name, destination):
        raise AssertionError("MinIO download should not run when local artifact exists")

    pipeline.download_artifact = download_artifact

    destination = tmp_path / "job" / "doc_middle.json"
    pipeline.stage_artifact("mds", "doc/auto/doc_middle.json", destination)

    assert destination.read_text(encoding="utf-8") == '{"from":"local"}'


def test_stage_artifact_falls_back_to_minio_when_local_artifact_is_missing(tmp_path):
    pipeline = PopoPipeline.__new__(PopoPipeline)
    pipeline.artifact_root = (tmp_path / "artifact-root").resolve()
    calls = []

    def download_artifact(bucket, object_name, destination):
        calls.append((bucket, object_name, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('{"from":"minio"}', encoding="utf-8")

    pipeline.download_artifact = download_artifact

    destination = tmp_path / "job" / "doc_middle.json"
    pipeline.stage_artifact("mds", "doc/auto/doc_middle.json", destination)

    assert destination.read_text(encoding="utf-8") == '{"from":"minio"}'
    assert calls == [("mds", "doc/auto/doc_middle.json", destination)]
