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
            markdown_name = self._find_markdown(names)
            if not markdown_name:
                raise ValueError("Markdown artifact not found in MinerU result")

            markdown = ""
            for name in names:
                target_path = self._target_path(prefix, name)
                content = archive.read(name)
                if name == markdown_name:
                    markdown = content.decode("utf-8")
                    markdown = self._rewrite_markdown_urls(markdown, prefix)
                    content = markdown.encode("utf-8")
                content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                self.minio.put_object(
                    self.bucket,
                    target_path,
                    io.BytesIO(content),
                    len(content),
                    content_type=content_type,
                )
                uploaded_paths.append(target_path)

        markdown_path = self._target_path(prefix, markdown_name)
        return SyncedArtifact(markdown=markdown, markdown_path=markdown_path, uploaded_paths=uploaded_paths)

    def _ensure_bucket(self) -> None:
        if not self.minio.bucket_exists(self.bucket):
            self.minio.make_bucket(self.bucket)

    @staticmethod
    def _safe_prefix(output_name: str) -> str:
        return output_name.replace("\\", "/").strip("/").replace("..", "")

    @staticmethod
    def _find_markdown(names: list[str]) -> str | None:
        md_files = [name for name in names if name.endswith(".md") and not name.endswith("_pages.md")]
        if md_files:
            return sorted(md_files, key=lambda item: (item.count("/"), len(item)))[0]
        page_md_files = [name for name in names if name.endswith(".md")]
        return sorted(page_md_files)[0] if page_md_files else None

    @staticmethod
    def _target_path(prefix: str, artifact_name: str) -> str:
        parts = artifact_name.split("/")
        if len(parts) > 1:
            artifact_name = "/".join(parts[1:])
        return posixpath.join(prefix, artifact_name)

    def _rewrite_markdown_urls(self, markdown: str, prefix: str) -> str:
        pattern = r"!\[([^\]]*)\]\(([^)]+)\)"

        def replace(match):
            alt = match.group(1)
            url = match.group(2)
            if url.startswith(("http://", "https://", "data:")):
                return match.group(0)
            image_path = posixpath.join(prefix, url.lstrip("./"))
            return f"![{alt}]({self.public_endpoint}/{self.bucket}/{image_path})"

        return re.sub(pattern, replace, markdown)
