"""MinerU API runtime patch for page-aware Markdown artifacts.

The business backend should not reimplement MinerU rendering rules. This patch
runs inside the MinerU API image and asks the installed MinerU package to render
each page with the backend-aware official renderer before result ZIPs are sent.
"""

from __future__ import annotations

import builtins
import json
import os
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any


_PATCHED = False
_ORIGINAL_IMPORT = builtins.__import__


def _page_heading(page_info: dict[str, Any], fallback_index: int) -> str:
    try:
        page_number = int(page_info.get("page_idx", fallback_index)) + 1
    except (TypeError, ValueError):
        page_number = fallback_index + 1
    return f"# Page {page_number}"


def _render_pages_markdown(middle_json_path: Path) -> str:
    from mineru.cli.client_side_output import PDF_BACKENDS, _select_union_make
    from mineru.utils.enum_class import MakeMode
    from mineru.utils.title_level_postprocess import finalize_client_side_middle_json

    middle_json = json.loads(middle_json_path.read_text(encoding="utf-8"))
    if not isinstance(middle_json, dict):
        return ""

    backend = middle_json.get("_backend")
    pdf_info = middle_json.get("pdf_info")
    if not isinstance(pdf_info, list):
        return ""

    if backend in PDF_BACKENDS:
        finalize_client_side_middle_json(middle_json)
        pdf_info = middle_json.get("pdf_info", [])

    make_func = _select_union_make(backend)
    page_markdowns: list[str] = []
    for index, page_info in enumerate(pdf_info):
        if not isinstance(page_info, dict):
            continue
        body = str(make_func([page_info], MakeMode.MM_MD, "images") or "").strip()
        page_markdowns.append(f"{_page_heading(page_info, index)}\n\n{body}".strip())

    return "\n\n".join(page for page in page_markdowns if page.strip()).strip()


def _ensure_pages_markdown(parse_dir: str, pdf_name: str) -> Path | None:
    parse_path = Path(parse_dir)
    pages_path = parse_path / f"{pdf_name}_pages.md"
    if pages_path.exists():
        return pages_path

    middle_json_path = parse_path / f"{pdf_name}_middle.json"
    if not middle_json_path.exists():
        return None

    markdown = _render_pages_markdown(middle_json_path)
    if not markdown:
        return None

    pages_path.write_text(markdown, encoding="utf-8")
    return pages_path


def _patch_fast_api(module: ModuleType) -> None:
    global _PATCHED
    if _PATCHED or getattr(module, "_mineru_web_pages_patch", False):
        return

    original_create_result_zip = getattr(module, "create_result_zip", None)
    get_parse_dir = getattr(module, "get_parse_dir", None)
    build_zip_arcname = getattr(module, "build_zip_arcname", None)
    if not original_create_result_zip or not get_parse_dir or not build_zip_arcname:
        return

    def create_result_zip_with_pages(
        output_dir: str,
        pdf_file_names: list[str],
        backend: str,
        parse_method: str,
        return_md: bool,
        return_middle_json: bool,
        return_model_output: bool,
        return_content_list: bool,
        return_images: bool,
        return_original_file: bool,
    ) -> str:
        pages_paths: list[tuple[str, str, Path]] = []
        if return_md:
            for pdf_name in pdf_file_names:
                try:
                    parse_dir = get_parse_dir(output_dir, pdf_name, backend, parse_method)
                    pages_path = _ensure_pages_markdown(parse_dir, pdf_name)
                except Exception as exc:
                    logger = getattr(module, "logger", None)
                    if logger:
                        logger.warning(f"Skipping pages Markdown generation for {pdf_name}: {exc}")
                    continue
                if pages_path:
                    pages_paths.append((pdf_name, parse_dir, pages_path))

        zip_path = original_create_result_zip(
            output_dir,
            pdf_file_names,
            backend,
            parse_method,
            return_md,
            return_middle_json,
            return_model_output,
            return_content_list,
            return_images,
            return_original_file,
        )

        if pages_paths:
            with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
                existing_names = set(zf.namelist())
                for pdf_name, parse_dir, pages_path in pages_paths:
                    arcname = build_zip_arcname(pdf_name, parse_dir, pages_path.name)
                    if arcname not in existing_names:
                        zf.write(str(pages_path), arcname=arcname)
                        existing_names.add(arcname)

        return zip_path

    module.create_result_zip = create_result_zip_with_pages
    module._mineru_web_pages_patch = True
    _PATCHED = True


def _try_patch_loaded_fast_api() -> None:
    module = sys.modules.get("mineru.cli.fast_api")
    if module:
        _patch_fast_api(module)


def _import_with_patch(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    if name == "mineru.cli.fast_api" or name.startswith("mineru.cli.fast_api."):
        _try_patch_loaded_fast_api()
    return module


if os.getenv("MINERU_WEB_DISABLE_PAGES_PATCH", "").lower() not in {"1", "true", "yes"}:
    builtins.__import__ = _import_with_patch
    _try_patch_loaded_fast_api()
