import io
import json
import os
import posixpath
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from minio import Minio

_MAX_STATUS_MESSAGE_LENGTH = 1024


def parse_minio_endpoint(endpoint: str) -> tuple[str, bool]:
    parsed = urlparse(endpoint)
    if parsed.scheme in {"http", "https"}:
        return parsed.netloc, parsed.scheme == "https"
    return endpoint, os.getenv("MINIO_SECURE", "false").lower() == "true"


_VISUAL_TYPES = {"image", "chart", "seal", "image_block"}
_SUPPLEMENT_TYPES = {"page_title", "page_number", "page_footnote", "header", "aside_text", "footer"}


def _image_path_of(item: dict[str, Any]) -> str:
    for key in ("img_path", "image_path", "image_url"):
        value = item.get(key)
        if value:
            return str(value).strip()
    return ""


def _table_html_of(item: dict[str, Any]) -> str:
    for key in ("table_body", "html", "table_html"):
        value = item.get(key)
        if value:
            return str(value).strip()
    return ""


def build_visual_map(
    content_list_path: Path,
    normalized_path: Path,
    content_list_object: str,
    image_base_url: str,
) -> dict[int, dict[str, str]]:
    """Recover image URLs and table HTML, keyed by the popo tree's block id.

    Image paths and table HTML are dropped during label normalization, so the
    popo tree keeps empty ``content`` for both. We rebuild the mapping by matching
    image/table blocks (in reading order, per page and per kind) between the
    normalized JSON — whose block ids are reproduced exactly the way
    ``inference.py`` assigns them — and the original MinerU ``content_list.json``
    which still carries ``img_path`` and ``table_body``.

    Table recovery needs no URL; image recovery needs ``image_base_url``. A
    one-line ``### MINERU-WEB-POPO ### visual`` diagnostic is always emitted so a
    single server run self-reports why the mapping is (or is not) built.
    """

    def log_diag(**fields: Any) -> None:
        summary = " ".join(f"{key}={value!r}" for key, value in fields.items())
        print(f"### MINERU-WEB-POPO ### visual {summary}", flush=True)

    if not content_list_path.is_file() or not normalized_path.is_file():
        log_diag(
            stage="precheck",
            content_list_exists=content_list_path.is_file(),
            normalized_exists=normalized_path.is_file(),
        )
        return {}

    content_list = json.loads(content_list_path.read_text(encoding="utf-8"))
    if not isinstance(content_list, list):
        log_diag(stage="content_list", error="not_a_list")
        return {}

    content_types: dict[str, int] = {}
    page_visuals: dict[int, dict[str, list[str]]] = {}
    for item in content_list:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type"))
        content_types[item_type] = content_types.get(item_type, 0) + 1
        page = int(item.get("page_idx", 0)) + 1
        if item_type == "image":
            page_visuals.setdefault(page, {}).setdefault("image", []).append(_image_path_of(item))
        elif item_type == "table":
            page_visuals.setdefault(page, {}).setdefault("table", []).append(_table_html_of(item))

    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    pages = normalized.get("pages", normalized) if isinstance(normalized, dict) else {}
    if not isinstance(pages, dict):
        log_diag(stage="normalized", error="no_pages")
        return {}

    base = image_base_url.rstrip("/") + "/" + posixpath.dirname(content_list_object) if image_base_url else ""
    visual_map: dict[int, dict[str, str]] = {}
    norm_counts = {"image": 0, "table": 0}
    matched = {"image": 0, "table": 0}
    block_id = 0
    page_rank: dict[tuple[int, str], int] = {}
    for page_num, blocks in pages.items():
        for block in blocks if isinstance(blocks, list) else []:
            block_id += 1
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type"))
            if block_type in _VISUAL_TYPES:
                kind = "image"
            elif block_type == "table":
                kind = "table"
            else:
                continue
            norm_counts[kind] += 1
            page = int(page_num)
            rank = page_rank.get((page, kind), 0)
            page_rank[(page, kind)] = rank + 1
            candidates = page_visuals.get(page, {}).get(kind, [])
            if rank >= len(candidates) or not candidates[rank]:
                continue
            if kind == "image":
                if base:
                    visual_map[block_id] = {"image_url": f"{base}/{candidates[rank].lstrip('/')}"}
                    matched["image"] += 1
            else:
                visual_map[block_id] = {"table_html": candidates[rank]}
                matched["table"] += 1

    sample = next(
        (entry.get("image_url") or entry.get("table_html", "")[:60] for entry in visual_map.values()),
        None,
    )
    log_diag(
        stage="done",
        content_types=content_types,
        has_base_url=bool(image_base_url),
        cl_images=sum(len(v.get("image", [])) for v in page_visuals.values()),
        cl_tables=sum(len(v.get("table", [])) for v in page_visuals.values()),
        norm_images=norm_counts["image"],
        norm_tables=norm_counts["table"],
        matched_images=matched["image"],
        matched_tables=matched["table"],
        base=base,
        sample=sample,
    )
    return visual_map


def render_popo_markdown(
    tree_path: Path,
    markdown_path: Path,
    visual_map: dict[int, dict[str, str]] | None = None,
) -> None:
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    visual_map = visual_map or {}
    lines: list[str] = []
    stats = {"table": 0, "table_empty": 0, "table_recovered": 0, "image": 0, "image_mapped": 0}

    def lookup(node: Any, key: str) -> str:
        for block_id in node.get("block_ids") or []:
            entry = visual_map.get(block_id) if isinstance(block_id, int) else None
            if entry and entry.get(key):
                return entry[key]
        return ""

    def append_content(content: Any) -> None:
        text = str(content or "").strip()
        if not text:
            return

        paragraphs = text.replace("<|txt_contd|>", "").split("<|txt_split|>")
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                lines.append(paragraph)
                lines.append("")

    def append_node(node: Any) -> None:
        if not isinstance(node, dict):
            return

        node_type = str(node.get("type") or "")
        title = str(node.get("title") or "").strip()

        if node_type == "root":
            pass
        elif node_type == "table":
            stats["table"] += 1
            if title:
                lines.append(f"**{title}**")
                lines.append("")
            content = str(node.get("content") or "").strip()
            if not content:
                content = lookup(node, "table_html")
                if content:
                    stats["table_recovered"] += 1
            if content:
                lines.append(content)
                lines.append("")
            else:
                stats["table_empty"] += 1
        elif node_type in _VISUAL_TYPES:
            stats["image"] += 1
            url = lookup(node, "image_url")
            if url:
                stats["image_mapped"] += 1
                lines.append(f"![{title or 'image'}]({url})")
            else:
                lines.append(f"[图片: {title}]" if title else "[图片]")
            lines.append("")
        elif node_type in _SUPPLEMENT_TYPES:
            pass
        else:
            if title and title not in {"Default Title", "N/A"}:
                level = _markdown_heading_level(node.get("level"))
                lines.append(f"{'#' * level} {title}")
                lines.append("")
            append_content(node.get("content"))

        for child in node.get("children") or []:
            append_node(child)

    append_node(tree)
    while lines and lines[-1] == "":
        lines.pop()

    print(
        "### MINERU-WEB-POPO ### render "
        f"tables={stats['table']} tables_recovered={stats['table_recovered']} "
        f"tables_still_empty={stats['table_empty']} "
        f"images={stats['image']} images_with_url={stats['image_mapped']}",
        flush=True,
    )

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _markdown_heading_level(value: Any) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return 2
    if level < 1:
        return 2
    return min(level, 6)


class PopoPipeline:
    def __init__(self) -> None:
        self.repo_dir = Path(os.getenv("POPO_REPO_DIR", "/opt/MinerU-Popo"))
        self.workspace = Path(os.getenv("POPO_WORKSPACE", "/workspace"))
        artifact_root = os.getenv("POPO_ARTIFACT_ROOT", "").strip()
        self.artifact_root = Path(artifact_root).resolve() if artifact_root else None

        endpoint, secure = parse_minio_endpoint(os.getenv("MINIO_ENDPOINT", "localhost:9000"))
        self.minio = Minio(
            endpoint,
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            secure=secure,
        )

    def run(self, request) -> dict[str, str]:
        job_dir = self.build_job_dir(request.prefix)

        try:
            self.write_status(request.bucket, request.outputs["status"], "processing", "")
            if job_dir.exists():
                shutil.rmtree(job_dir)

            vlm_dir = job_dir / "post-process" / "mineru" / request.prefix / "vlm"
            vlm_dir.mkdir(parents=True, exist_ok=True)

            self.stage_artifact(
                request.bucket,
                request.artifacts["middle_json"],
                vlm_dir / f"{request.prefix}_middle.json",
            )
            self.stage_artifact(
                request.bucket,
                request.artifacts["content_list_json"],
                vlm_dir / f"{request.prefix}_content_list.json",
            )
            source_pdf_path = job_dir / "source" / f"{request.prefix}.pdf"
            self.stage_artifact(
                getattr(request, "source_bucket", None) or request.bucket,
                request.artifacts["source_pdf"],
                source_pdf_path,
            )
            pdf_map_path = job_dir / "pdf-map.json"
            pdf_map_path.write_text(
                json.dumps({request.prefix: str(source_pdf_path)}, ensure_ascii=False),
                encoding="utf-8",
            )

            self.run_popo_commands(job_dir, request.prefix)

            json_path = job_dir / "outputs" / "build_tree" / "mineru" / f"{request.prefix}.json"
            markdown_path = job_dir / "outputs" / "markdown" / "mineru" / f"{request.prefix}.md"

            image_base_url = os.getenv("POPO_IMAGE_BASE_URL", "")
            content_list_object = request.artifacts.get("content_list_json", "")
            visual_map = build_visual_map(
                vlm_dir / f"{request.prefix}_content_list.json",
                job_dir / "outputs" / "label_normalization" / "mineru" / f"{request.prefix}.json",
                content_list_object,
                image_base_url,
            )
            render_popo_markdown(json_path, markdown_path, visual_map)

            self.upload_file(
                request.bucket,
                request.outputs["json"],
                json_path,
                "application/json",
            )
            self.upload_file(
                request.bucket,
                request.outputs["markdown"],
                markdown_path,
                "text/markdown; charset=utf-8",
            )
            self.write_status(request.bucket, request.outputs["status"], "success", "")
        except Exception as exc:
            message = str(exc)[:_MAX_STATUS_MESSAGE_LENGTH]
            try:
                self.write_status(request.bucket, request.outputs["status"], "failed", message)
            except Exception:
                pass
            raise

        return {
            "status": "success",
            "markdown_path": request.outputs["markdown"],
            "json_path": request.outputs["json"],
        }

    def build_job_dir(self, prefix: str) -> Path:
        prefix_path = Path(prefix)
        if not prefix or prefix_path.is_absolute() or any(part in {"", ".."} for part in prefix_path.parts):
            raise ValueError("Invalid Popo prefix")
        if len(prefix_path.parts) != 1:
            raise ValueError("Invalid Popo prefix")

        workspace = self.workspace.resolve()
        job_dir = (workspace / prefix).resolve()
        if job_dir == workspace or workspace not in job_dir.parents:
            raise ValueError("Invalid Popo prefix")
        return job_dir

    def stage_artifact(self, bucket: str, object_name: str, destination: Path) -> None:
        local_path = self.resolve_local_artifact(object_name)
        if local_path is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local_path, destination)
            return

        self.download_artifact(bucket, object_name, destination)

    def resolve_local_artifact(self, object_name: str) -> Path | None:
        artifact_root = getattr(self, "artifact_root", None)
        if artifact_root is None:
            return None

        object_path = Path(object_name)
        if object_path.is_absolute() or any(part in {"", ".."} for part in object_path.parts):
            return None

        candidate = (artifact_root / object_path).resolve()
        if artifact_root not in candidate.parents and candidate != artifact_root:
            return None
        return candidate if candidate.is_file() else None

    def download_artifact(self, bucket: str, object_name: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self.minio.get_object(bucket, object_name)
        try:
            with destination.open("wb") as output:
                for chunk in response.stream(32 * 1024):
                    output.write(chunk)
        finally:
            response.close()
            response.release_conn()

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        source: Path,
        content_type: str,
    ) -> None:
        self.minio.fput_object(
            bucket,
            object_name,
            str(source),
            content_type=content_type,
        )

    def write_status(self, bucket: str, object_name: str, status: str, message: str) -> None:
        payload = json.dumps({"status": status, "message": message}, ensure_ascii=False).encode("utf-8")
        self.minio.put_object(
            bucket,
            object_name,
            data=io.BytesIO(payload),
            length=len(payload),
            content_type="application/json",
        )

    def run_popo_commands(self, job_dir: Path, doc_id: str) -> None:
        subprocess.run(
            [
                "python3",
                str(self.repo_dir / "post_processing" / "label_normalization.py"),
                "--model",
                "mineru",
                "--input-dir",
                str(job_dir / "post-process" / "mineru"),
                "--output-dir",
                str(job_dir / "outputs" / "label_normalization"),
                "--doc-id",
                doc_id,
                "--doc-limit",
                "0",
                "--pdf-map-json",
                str(job_dir / "pdf-map.json"),
            ],
            cwd=self.repo_dir,
            check=True,
        )
        self.log_inference_candidate_summary(job_dir, doc_id)
        subprocess.run(
            [
                "python3",
                str(self.repo_dir / "post_processing" / "run_inference.py"),
                "--model",
                "mineru",
                "--input-dir",
                str(job_dir / "outputs" / "label_normalization" / "mineru"),
                "--output-dir",
                str(job_dir / "outputs" / "inference" / "mineru"),
                "--raw-output-root",
                "",
                "--limit",
                "0",
            ],
            cwd=self.repo_dir,
            check=True,
        )
        subprocess.run(
            [
                "python3",
                str(self.repo_dir / "post_processing" / "get_json_tree.py"),
                "--input-dir",
                str(job_dir / "outputs" / "inference" / "mineru"),
                "--output-dir",
                str(job_dir / "outputs" / "build_tree" / "mineru"),
                "--txt-dir",
                str(job_dir / "outputs" / "build_tree_txt" / "mineru"),
            ],
            cwd=self.repo_dir,
            check=True,
        )

    def log_inference_candidate_summary(self, job_dir: Path, doc_id: str) -> None:
        doc_name = Path(doc_id).name
        script = f"""
import json
import sys
from pathlib import Path

repo_dir = Path({str(self.repo_dir)!r})
input_path = Path({str(job_dir / "outputs" / "label_normalization" / "mineru" / f"{doc_id}.json")!r})
sys.path.insert(0, str(repo_dir / "post_processing"))
sys.path.insert(0, str(repo_dir / "data_engine"))

from inference import (
    adaptive_chunk,
    add_contd,
    add_image,
    add_title,
    filter_contd,
    filter_image,
    filter_table_merge,
    filter_title,
    parse_string_notype,
    parse_string_type,
)

payload = json.loads(input_path.read_text(encoding="utf-8"))
pages = payload.get("pages", payload)
doc_blocks = []
idx = 1
for page_num, blocks in pages.items():
    for block in blocks:
        block = dict(block)
        block["page"] = int(page_num)
        block["id"] = idx
        block.setdefault("contd", -1)
        block.setdefault("level", -1)
        block.setdefault("image", -1)
        idx += 1
        doc_blocks.append(block)

contd = filter_contd(doc_blocks)
title = filter_title(doc_blocks)
image, _ = filter_image(doc_blocks)
table_merge = filter_table_merge(doc_blocks)
_, contd_chunks = adaptive_chunk(parse_string_notype(add_contd(contd)))
_, title_chunks = adaptive_chunk(parse_string_notype(add_title(title)))
_, image_chunks = adaptive_chunk(parse_string_type(add_image(image)))
print(
    "### MINERU-WEB-POPO ### candidates "
    f"doc={doc_name!r} blocks={{len(doc_blocks)}} "
    f"contd={{len(contd)}} contd_chunks={{len(contd_chunks)}} "
    f"title={{len(title)}} title_chunks={{len(title_chunks)}} "
    f"image={{len(image)}} image_chunks={{len(image_chunks)}} "
    f"table_merge={{len(table_merge)}}",
    flush=True,
)
"""
        subprocess.run(["python3", "-c", script], cwd=self.repo_dir, check=True)
