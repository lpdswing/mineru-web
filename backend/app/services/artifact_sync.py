import io
import mimetypes
import posixpath
import re
import zipfile
from dataclasses import dataclass


@dataclass
class SyncedArtifact:
    markdown: str
    markdown_path: str
    uploaded_paths: list[str]


class MineruArtifactSync:
    def __init__(self, minio, bucket: str, endpoint: str, public_endpoint: str | None = None):
        self.minio = minio
        self.bucket = bucket
        self.endpoint = endpoint.rstrip("/")
        self.public_endpoint = (public_endpoint or endpoint).rstrip("/")

    def sync_zip(self, zip_bytes: bytes, output_name: str) -> SyncedArtifact:
        self._ensure_bucket()
        uploaded_paths: list[str] = []
        prefix = self._safe_prefix(output_name)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            markdown_name = self._find_markdown(names, prefix)
            if not markdown_name:
                raise ValueError("Markdown artifact not found in MinerU result")

            markdown = ""
            for name in names:
                target_path = self._artifact_path(prefix, name)
                content = archive.read(name)
                content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"

                if name.endswith(".md"):
                    markdown_content = content.decode("utf-8")
                    markdown_base_path = posixpath.dirname(target_path)
                    markdown_content = self._rewrite_markdown_urls(markdown_content, markdown_base_path)
                    content = markdown_content.encode("utf-8")
                    if name == markdown_name:
                        markdown = markdown_content
                        export_path = self._export_markdown_path(prefix, name)
                        uploaded_paths.extend(self._put_object(export_path, content, content_type))
                    elif name.endswith("_pages.md"):
                        export_path = self._export_markdown_path(prefix, name)
                        uploaded_paths.extend(self._put_object(export_path, content, content_type))
                    else:
                        export_path = None

                    if target_path != export_path:
                        uploaded_paths.extend(self._put_object(target_path, content, content_type))
                    continue

                uploaded_paths.extend(self._put_object(target_path, content, content_type))

        markdown_path = self._export_markdown_path(prefix, markdown_name)
        return SyncedArtifact(markdown=markdown, markdown_path=markdown_path, uploaded_paths=uploaded_paths)

    def _ensure_bucket(self) -> None:
        if not self.minio.bucket_exists(self.bucket):
            self.minio.make_bucket(self.bucket)

    @staticmethod
    def _safe_prefix(output_name: str) -> str:
        return output_name.replace("\\", "/").strip("/").replace("..", "")

    @staticmethod
    def _find_markdown(names: list[str], prefix: str) -> str | None:
        md_files = [name for name in names if name.endswith(".md") and not name.endswith("_pages.md")]
        if md_files:
            expected_stem = posixpath.basename(prefix)
            return sorted(
                md_files,
                key=lambda item: (
                    posixpath.splitext(posixpath.basename(item))[0] != expected_stem,
                    item.count("/"),
                    len(item),
                ),
            )[0]
        page_md_files = [name for name in names if name.endswith(".md")]
        return sorted(page_md_files)[0] if page_md_files else None

    @staticmethod
    def _artifact_path(prefix: str, artifact_name: str) -> str:
        parts = artifact_name.split("/")
        if len(parts) > 1:
            artifact_name = "/".join(parts[1:])
        return posixpath.join(prefix, artifact_name)

    @staticmethod
    def _export_markdown_path(prefix: str, artifact_name: str) -> str:
        if artifact_name.endswith("_pages.md"):
            return f"{prefix}_pages.md"
        return f"{prefix}.md"

    def _put_object(self, path: str, content: bytes, content_type: str) -> list[str]:
        self.minio.put_object(
            self.bucket,
            path,
            io.BytesIO(content),
            len(content),
            content_type=content_type,
        )
        return [path]

    def _rewrite_markdown_urls(self, markdown: str, markdown_base_path: str) -> str:
        pattern = r"!\[([^\]]*)\]\(([^)]+)\)"

        def replace(match):
            alt = match.group(1)
            url = match.group(2)
            if url.startswith(("http://", "https://", "data:")):
                return match.group(0)
            relative_url = url.lstrip("/")
            image_path = posixpath.normpath(posixpath.join(markdown_base_path, relative_url))
            return f"![{alt}]({self.public_endpoint}/{self.bucket}/{image_path})"

        return re.sub(pattern, replace, markdown)
