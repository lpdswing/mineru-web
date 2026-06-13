import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType


def load_patch_module(monkeypatch):
    monkeypatch.setenv("MINERU_WEB_DISABLE_PAGES_PATCH", "1")
    path = Path(__file__).parents[1] / "mineru_api_patch" / "sitecustomize.py"
    spec = importlib.util.spec_from_file_location("mineru_api_pages_patch_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pages_patch_appends_generated_page_markdown(monkeypatch, tmp_path):
    patch = load_patch_module(monkeypatch)
    parse_dir = tmp_path / "sample" / "auto"
    parse_dir.mkdir(parents=True)
    pages_path = parse_dir / "sample_pages.md"
    pages_path.write_text("# Page 1\n\nBody", encoding="utf-8")

    zip_path = tmp_path / "result.zip"

    fake_fast_api = ModuleType("mineru.cli.fast_api")

    def create_result_zip(*args, **kwargs):
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("sample/auto/sample.md", "# Main")
        return str(zip_path)

    fake_fast_api.create_result_zip = create_result_zip
    fake_fast_api.get_parse_dir = lambda output_dir, pdf_name, backend, parse_method: str(parse_dir)
    fake_fast_api.build_zip_arcname = lambda pdf_name, parse_dir_arg, rel: f"{pdf_name}/auto/{rel}"

    monkeypatch.setattr(patch, "_ensure_pages_markdown", lambda parse_dir_arg, pdf_name: pages_path)

    patch._patch_fast_api(fake_fast_api)
    result_path = fake_fast_api.create_result_zip(
        str(tmp_path),
        ["sample"],
        "pipeline",
        "auto",
        True,
        True,
        True,
        True,
        True,
        False,
    )

    with zipfile.ZipFile(io.BytesIO(Path(result_path).read_bytes())) as archive:
        assert archive.read("sample/auto/sample_pages.md") == b"# Page 1\n\nBody"


def test_pages_patch_renders_pages_with_backend_aware_mineru_renderer(monkeypatch, tmp_path):
    patch = load_patch_module(monkeypatch)
    calls = []

    client_side_output = ModuleType("mineru.cli.client_side_output")
    client_side_output.PDF_BACKENDS = {"pipeline", "vlm", "hybrid"}

    def select_union_make(backend):
        def union_make(pdf_info, make_mode, image_dir):
            calls.append((backend, make_mode, image_dir, pdf_info[0]["page_idx"]))
            return f"{backend}:{pdf_info[0]['text']}"

        return union_make

    client_side_output._select_union_make = select_union_make

    enum_class = ModuleType("mineru.utils.enum_class")

    class MakeMode:
        MM_MD = "mm_md"

    enum_class.MakeMode = MakeMode

    title_level_postprocess = ModuleType("mineru.utils.title_level_postprocess")
    title_level_postprocess.finalize_client_side_middle_json = lambda middle_json: None

    monkeypatch.setitem(sys.modules, "mineru.cli.client_side_output", client_side_output)
    monkeypatch.setitem(sys.modules, "mineru.utils.enum_class", enum_class)
    monkeypatch.setitem(sys.modules, "mineru.utils.title_level_postprocess", title_level_postprocess)

    middle_json_path = tmp_path / "sample_middle.json"
    middle_json_path.write_text(
        json.dumps(
            {
                "_backend": "vlm",
                "pdf_info": [
                    {"page_idx": 0, "text": "one"},
                    {"page_idx": 2, "text": "three"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert patch._render_pages_markdown(middle_json_path) == (
        "# Page 1\n\nvlm:one\n\n# Page 3\n\nvlm:three"
    )
    assert calls == [
        ("vlm", "mm_md", "images", 0),
        ("vlm", "mm_md", "images", 2),
    ]
