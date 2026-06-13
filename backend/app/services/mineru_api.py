import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


class MineruApiError(Exception):
    """Base error for MinerU API failures."""


class MineruApiUnavailable(MineruApiError):
    """Raised when the MinerU API service cannot be reached."""


class MineruApiTimeout(MineruApiError):
    """Raised when the MinerU API request or task polling times out."""


@dataclass
class MineruParseResult:
    filename: str
    content: bytes
    content_type: str


class MineruApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
        task_timeout_seconds: float | None = None,
        use_async_tasks: bool | None = None,
        server_url: str | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = (base_url or os.getenv("MINERU_API_URL", "http://mineru-router:8002")).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(os.getenv("MINERU_API_TIMEOUT_SECONDS", "300"))
        self.poll_interval_seconds = poll_interval_seconds or float(os.getenv("MINERU_API_POLL_INTERVAL_SECONDS", "2"))
        self.task_timeout_seconds = task_timeout_seconds or float(os.getenv("MINERU_API_TASK_TIMEOUT_SECONDS", "1800"))
        self.use_async_tasks = (
            use_async_tasks
            if use_async_tasks is not None
            else os.getenv("MINERU_API_USE_ASYNC_TASKS", "0") == "1"
        )
        self.server_url = server_url or os.getenv("SERVER_URL") or os.getenv("MINERU_API_SERVER_URL")
        self.http_client = http_client or httpx.Client(timeout=self.timeout_seconds)

    def health(self) -> dict[str, Any]:
        try:
            response = self.http_client.get(f"{self.base_url}/health")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                payload = {"raw": payload}
            return {"available": True, "base_url": self.base_url, **payload}
        except Exception as exc:
            return {"available": False, "base_url": self.base_url, "error": str(exc)}

    def parse_file(
        self,
        filename: str,
        file_bytes: bytes,
        backend: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
        progress_callback=None,
    ) -> MineruParseResult:
        if self.use_async_tasks:
            return self._parse_file_async(
                filename,
                file_bytes,
                backend,
                parse_method,
                lang,
                formula_enable,
                table_enable,
                progress_callback=progress_callback,
            )
        return self._parse_file_sync(
            filename,
            file_bytes,
            backend,
            parse_method,
            lang,
            formula_enable,
            table_enable,
        )

    def _parse_file_sync(
        self,
        filename: str,
        file_bytes: bytes,
        backend: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
    ) -> MineruParseResult:
        data = self._form_data(backend, parse_method, lang, formula_enable, table_enable)
        files = {"files": (filename, file_bytes, "application/octet-stream")}
        response = self._request("post", "/file_parse", data=data, files=files)
        return MineruParseResult(
            filename=filename,
            content=response.content,
            content_type=response.headers.get("content-type", ""),
        )

    def _parse_file_async(
        self,
        filename: str,
        file_bytes: bytes,
        backend: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
        progress_callback=None,
    ) -> MineruParseResult:
        data = self._form_data(backend, parse_method, lang, formula_enable, table_enable)
        files = {"files": (filename, file_bytes, "application/octet-stream")}
        submit = self._request("post", "/tasks", data=data, files=files).json()
        task_id = submit.get("task_id") or submit.get("id")
        if not task_id:
            raise MineruApiError(f"MinerU API task response missing task id: {submit}")
        if progress_callback:
            progress_callback({"task_id": task_id, "status": "submitted", "payload": submit})

        deadline = time.time() + self.task_timeout_seconds
        while time.time() < deadline:
            status_payload = self._request("get", f"/tasks/{task_id}").json()
            status = str(status_payload.get("status", "")).lower()
            if status in {"done", "completed", "success", "finished"}:
                if progress_callback:
                    progress_callback(
                        {
                            "task_id": task_id,
                            "status": status,
                            "stage": "downloading_result",
                            "message": "正在下载解析结果",
                            "payload": status_payload,
                        }
                    )
                result = self._request("get", f"/tasks/{task_id}/result")
                return MineruParseResult(
                    filename=filename,
                    content=result.content,
                    content_type=result.headers.get("content-type", ""),
                )
            if progress_callback:
                progress_callback({"task_id": task_id, "status": status, "payload": status_payload})
            if status in {"failed", "error", "cancelled"}:
                raise MineruApiError(f"MinerU API task {task_id} failed: {status_payload}")
            time.sleep(self.poll_interval_seconds)

        raise MineruApiTimeout(f"MinerU API task {task_id} exceeded {self.task_timeout_seconds} seconds")

    def _form_data(
        self,
        backend: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
    ) -> dict[str, str]:
        data = {
            "backend": backend,
            "parse_method": parse_method,
            "lang_list": lang,
            "formula_enable": str(formula_enable).lower(),
            "table_enable": str(table_enable).lower(),
            "return_md": "true",
            "return_middle_json": "true",
            "return_model_output": "true",
            "return_content_list": "true",
            "return_images": "true",
            "response_format_zip": "true",
        }
        if self.server_url:
            data["server_url"] = self.server_url
        return data

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.http_client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            raise MineruApiTimeout(f"MinerU API request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise MineruApiUnavailable(f"MinerU API unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise MineruApiError(self._status_error_message(exc.response)) from exc

    @staticmethod
    def _status_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        return f"MinerU API returned {response.status_code}: {payload}"
