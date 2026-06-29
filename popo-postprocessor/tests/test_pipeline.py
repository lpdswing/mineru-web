import json
from types import SimpleNamespace

from app.pipeline import build_visual_map
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


def test_render_popo_markdown_renders_table_as_inline_html(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        """
        {
          "type": "root",
          "children": [
            {
              "type": "table",
              "title": "表 1 销售数据",
              "content": "<table><tr><th>产品</th><th>金额</th></tr><tr><td>A</td><td>100</td></tr></table>",
              "children": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    render_popo_markdown(tree_path, markdown_path)

    result = markdown_path.read_text(encoding="utf-8")
    assert "**表 1 销售数据**" in result
    assert "<table>" in result
    assert "<tr>" in result


def test_render_popo_markdown_renders_table_without_caption(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        """
        {
          "type": "root",
          "children": [
            {
              "type": "table",
              "title": "",
              "content": "<table><tr><td>A</td></tr></table>",
              "children": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    render_popo_markdown(tree_path, markdown_path)

    result = markdown_path.read_text(encoding="utf-8")
    assert "<table>" in result
    assert "**" not in result


def test_render_popo_markdown_renders_image_placeholder_with_caption(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        """
        {
          "type": "root",
          "children": [
            {
              "type": "image",
              "title": "图 1 系统架构图",
              "content": "",
              "children": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    render_popo_markdown(tree_path, markdown_path)

    assert markdown_path.read_text(encoding="utf-8") == "[图片: 图 1 系统架构图]\n"


def test_build_visual_map_matches_images_and_tables_per_page_and_kind(tmp_path):
    content_list_path = tmp_path / "doc_content_list.json"
    normalized_path = tmp_path / "doc.json"
    content_list_path.write_text(
        json.dumps(
            [
                {"type": "text", "text": "正文", "page_idx": 0},
                {"type": "image", "img_path": "images/a.jpg", "page_idx": 0},
                {"type": "table", "table_body": "<table><tr><td>1</td></tr></table>", "page_idx": 0},
                {"type": "image", "img_path": "images/b.jpg", "page_idx": 1},
            ]
        ),
        encoding="utf-8",
    )
    normalized_path.write_text(
        json.dumps(
            {
                "pages": {
                    "1": [
                        {"type": "text", "content": "正文"},
                        {"type": "image", "content": ""},
                        {"type": "table", "content": ""},
                    ],
                    "2": [
                        {"type": "image", "content": ""},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    result = build_visual_map(
        content_list_path,
        normalized_path,
        "doc/auto/doc_content_list.json",
        "http://localhost:9000/mds",
    )

    assert result == {
        2: {"image_url": "http://localhost:9000/mds/doc/auto/images/a.jpg"},
        3: {"table_html": "<table><tr><td>1</td></tr></table>"},
        4: {"image_url": "http://localhost:9000/mds/doc/auto/images/b.jpg"},
    }


def test_build_visual_map_recovers_tables_without_base_url(tmp_path):
    content_list_path = tmp_path / "doc_content_list.json"
    normalized_path = tmp_path / "doc.json"
    content_list_path.write_text(
        json.dumps(
            [
                {"type": "table", "table_body": "<table><tr><td>x</td></tr></table>", "page_idx": 0},
                {"type": "image", "img_path": "images/a.jpg", "page_idx": 0},
            ]
        ),
        encoding="utf-8",
    )
    normalized_path.write_text(
        json.dumps({"pages": {"1": [{"type": "table"}, {"type": "image"}]}}),
        encoding="utf-8",
    )

    result = build_visual_map(content_list_path, normalized_path, "doc/x.json", "")

    # Table HTML needs no URL; images are skipped when base_url is absent.
    assert result == {1: {"table_html": "<table><tr><td>x</td></tr></table>"}}


def test_render_popo_markdown_renders_real_image_url_when_mapped(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        """
        {
          "type": "root",
          "children": [
            {"type": "image", "title": "图 1 架构图", "content": "", "block_ids": [2], "children": []}
          ]
        }
        """,
        encoding="utf-8",
    )

    render_popo_markdown(
        tree_path,
        markdown_path,
        {2: {"image_url": "http://localhost:9000/mds/doc/auto/images/a.jpg"}},
    )

    assert markdown_path.read_text(encoding="utf-8") == (
        "![图 1 架构图](http://localhost:9000/mds/doc/auto/images/a.jpg)\n"
    )


def test_render_popo_markdown_recovers_empty_table_html_from_visual_map(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        """
        {
          "type": "root",
          "children": [
            {"type": "table", "title": "表 1", "content": "", "block_ids": [5], "children": []}
          ]
        }
        """,
        encoding="utf-8",
    )

    render_popo_markdown(
        tree_path,
        markdown_path,
        {5: {"table_html": "<table><tr><td>v</td></tr></table>"}},
    )

    result = markdown_path.read_text(encoding="utf-8")
    assert "**表 1**" in result
    assert "<table><tr><td>v</td></tr></table>" in result


def test_render_popo_markdown_falls_back_to_placeholder_when_block_id_unmapped(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        '{"type":"root","children":[{"type":"image","title":"图1","content":"","block_ids":[9],"children":[]}]}',
        encoding="utf-8",
    )

    render_popo_markdown(tree_path, markdown_path, {2: {"image_url": "http://x/a.jpg"}})

    assert markdown_path.read_text(encoding="utf-8") == "[图片: 图1]\n"


def test_render_popo_markdown_renders_image_placeholder_without_caption(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        '{"type":"root","children":[{"type":"image","title":"","content":"","children":[]}]}',
        encoding="utf-8",
    )

    render_popo_markdown(tree_path, markdown_path)

    assert markdown_path.read_text(encoding="utf-8") == "[图片]\n"


def test_render_popo_markdown_renders_chart_and_seal_as_image_placeholder(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        """
        {
          "type": "root",
          "children": [
            {"type": "chart", "title": "销售趋势图", "content": "", "children": []},
            {"type": "seal",  "title": "",            "content": "", "children": []}
          ]
        }
        """,
        encoding="utf-8",
    )

    render_popo_markdown(tree_path, markdown_path)

    result = markdown_path.read_text(encoding="utf-8")
    assert "[图片: 销售趋势图]" in result
    assert "[图片]" in result


def test_render_popo_markdown_skips_supplement_types(tmp_path):
    tree_path = tmp_path / "doc.json"
    markdown_path = tmp_path / "doc.md"
    tree_path.write_text(
        """
        {
          "type": "root",
          "children": [
            {"type": "text", "title": "正文", "level": 1, "content": "正文内容", "children": []},
            {"type": "header",       "title": "Page 1 - header",       "content": "页眉文字", "children": []},
            {"type": "footer",       "title": "Page 1 - footer",       "content": "页脚文字", "children": []},
            {"type": "page_number",  "title": "Page 1 - page_number",  "content": "1",       "children": []},
            {"type": "page_title",   "title": "Page 1 - page_title",   "content": "封面标题", "children": []},
            {"type": "page_footnote","title": "Page 1 - page_footnote","content": "脚注内容", "children": []},
            {"type": "aside_text",   "title": "Page 1 - aside_text",   "content": "边栏文字", "children": []}
          ]
        }
        """,
        encoding="utf-8",
    )

    render_popo_markdown(tree_path, markdown_path)

    result = markdown_path.read_text(encoding="utf-8")
    assert "正文内容" in result
    for noise in ("页眉文字", "页脚文字", "1", "封面标题", "脚注内容", "边栏文字", "Page 1"):
        assert noise not in result


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
