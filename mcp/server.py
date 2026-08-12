"""
MinerU Web Service - MCP Server (HTTP/SSE)

把后端的 HTTP API 包装成 MCP 工具，供 LLM 客户端（如 Claude Code）程序化调用。
通过 SSE 传输对外暴露，默认 :8001，SSE 流端点 /sse。

走本地解析路径：/api/upload → 轮询 /api/files/{id}/parse/status → /api/files/{id}/parsed_content。
解析由后端 worker 调用本地 mineru-api（910B NPU）完成，不依赖 mineru.net 云端。

认证：用 MINERU_AUTH_USER / MINERU_AUTH_PASS 登录拿 session token，401 自动重登。
环境变量：
  BACKEND_URL        后端地址（容器内默认 http://backend:8000）
  MINERU_AUTH_USER   登录邮箱（必填）
  MINERU_AUTH_PASS   登录密码（必填）
"""
import os
import re
import json
import asyncio

import httpx
from fastmcp import FastMCP

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000").rstrip("/")
AUTH_USER = os.environ.get("MINERU_AUTH_USER", "")
AUTH_PASS = os.environ.get("MINERU_AUTH_PASS", "")
POLL_INTERVAL = 3
POLL_TIMEOUT = 60 * 30     # 本地 NPU 解析可能较慢，最长等 30 分钟
SESSION_COOKIE = "mineru_session"

if not AUTH_USER or not AUTH_PASS:
    # 不 sys.exit：让 SSE 端点照常起来，docker compose ps 能看到服务、日志能 grep 到这条警告。
    # 未填时首次工具调用会在 _login 抛错。
    print("[mineru-mcp] 警告：MINERU_AUTH_USER / MINERU_AUTH_PASS 未设置，工具调用将失败", flush=True)

mcp = FastMCP("mineru")

# 进程内 token 缓存。token 有效期由后端 AUTH_COOKIE_MAX_AGE_SECONDS 控制（默认 7 天）。
_token_lock = asyncio.Lock()
_cached_token: str | None = None


async def _login() -> str:
    if not AUTH_USER or not AUTH_PASS:
        raise RuntimeError("MINERU_AUTH_USER / MINERU_AUTH_PASS 未设置")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{BACKEND_URL}/api/auth/login",
            json={"email": AUTH_USER, "password": AUTH_PASS},
        )
        r.raise_for_status()
        token = r.cookies.get(SESSION_COOKIE)
        if not token:
            raise RuntimeError(f"登录响应未包含 {SESSION_COOKIE} cookie")
        return token


async def _get_token() -> str:
    global _cached_token
    async with _token_lock:
        if _cached_token is None:
            _cached_token = await _login()
        return _cached_token


async def _invalidate_token() -> None:
    global _cached_token
    async with _token_lock:
        _cached_token = None


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    """带认证的请求。401 时清缓存重新登录，最多重试一次。"""
    token = await _get_token()
    headers = kwargs.pop("headers", {}) or {}
    r: httpx.Response
    for attempt in range(2):
        headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.request(method, f"{BACKEND_URL}{path}", headers=headers, **kwargs)
        if r.status_code != 401 or attempt:
            return r
        await _invalidate_token()
        token = await _get_token()
    return r


def _normalize_path(path: str) -> str:
    """归一化路径。file_path 必须是 mcp 容器内可见的路径：
    - 裸文件名 -> '/inbox/<name>'（compose 已把宿主 ./inbox 只读挂载到 /inbox）；
    - '/xxx' 绝对路径原样返回（对应宿主目录需自行在 compose 里挂载）；
    - Windows 盘符路径无效——宿主文件须先挂载进容器，这里直接抛错而不是静默映射到不存在的路径。
    """
    p = path.strip()
    if re.match(r"^[a-zA-Z]:", p):
        raise ValueError(
            f"file_path 必须是 mcp 容器内路径，收到 Windows 路径 {p!r}。"
            "请把宿主目录挂载进 mcp 容器（默认 ./inbox:/inbox）后传容器内路径，如 /inbox/foo.pdf。"
        )
    if p.startswith("/"):
        return p
    return f"/inbox/{p}"


async def _parse_bytes(filename: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """上传到后端本地接口，轮询解析状态，返回 Markdown。"""
    # 1. upload（upload 后后端自动把任务入队给 worker）
    files = {"files": (filename, data, content_type)}
    r = await _request("POST", "/api/upload", files=files)
    r.raise_for_status()
    uploaded = r.json().get("files") or []
    if not uploaded:
        raise RuntimeError("上传未返回文件记录，后端 /api/upload 响应里没有 files 字段")
    file_id = uploaded[0]["id"]

    # 2. 轮询 parse/status
    elapsed = 0
    parsed = False
    while elapsed < POLL_TIMEOUT:
        r = await _request("GET", f"/api/files/{file_id}/parse/status")
        r.raise_for_status()
        detail = r.json()
        status = detail.get("status")
        if status == "parsed":
            parsed = True
            break
        if status in ("parse_failed", "failed"):
            raise RuntimeError(f"解析失败 file_id={file_id}：{detail.get('message') or detail}")
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    if not parsed:
        raise RuntimeError(f"解析超时 file_id={file_id}(>{POLL_TIMEOUT}s)，仍可能在解析，可用 get_result({file_id}) 轮询")

    # 3. 取 Markdown
    r = await _request("GET", f"/api/files/{file_id}/parsed_content", params={"variant": "markdown"})
    r.raise_for_status()
    content = r.json()
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


@mcp.tool()
async def parse_document(file_path: str) -> str:
    """解析本地文档（PDF/图片）。file_path 必须是 mcp 容器内可见的路径：
    ./inbox 下的文件可直接传裸文件名；其他位置传容器内绝对路径（需自行挂载对应宿主目录）。
    Windows 盘符路径无效。返回解析后的 Markdown；上传/解析失败或超时会抛错。"""
    p = _normalize_path(file_path)
    with open(p, "rb") as f:
        data = f.read()
    return await _parse_bytes(os.path.basename(p), data)


@mcp.tool()
async def parse_document_url(url: str) -> str:
    """从 URL 下载文档并经本地 MinerU（910B NPU）解析。返回解析后的 Markdown。"""
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url)
        r.raise_for_status()
        data = r.content
        filename = url.rsplit("/", 1)[-1].split("?")[0] or "document"
    return await _parse_bytes(filename, data)


@mcp.tool()
async def list_files() -> str:
    """列出当前用户的所有文件记录及其状态。"""
    r = await _request("GET", "/api/files")
    r.raise_for_status()
    return json.dumps(r.json(), ensure_ascii=False)


@mcp.tool()
async def get_result(file_id: int) -> str:
    """按 id 获取某文件的解析状态与 Markdown（已解析时返回内容，否则只返回状态）。"""
    r = await _request("GET", f"/api/files/{file_id}/parse/status")
    r.raise_for_status()
    status = r.json()
    markdown = ""
    if status.get("status") == "parsed":
        rr = await _request("GET", f"/api/files/{file_id}/parsed_content", params={"variant": "markdown"})
        if rr.status_code == 200:
            c = rr.json()
            markdown = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
    return json.dumps({"status": status, "markdown": markdown}, ensure_ascii=False)


@mcp.tool()
async def get_content_list(file_id: int) -> str:
    """按 id 获取结构化 content_list（带类型/文本/bbox 的块列表）。"""
    r = await _request("GET", f"/api/files/{file_id}/content")
    r.raise_for_status()
    return json.dumps(r.json(), ensure_ascii=False)


@mcp.tool()
async def delete_file(file_id: int) -> str:
    """按 id 删除文件记录及其存储对象。"""
    r = await _request("DELETE", f"/api/files/{file_id}")
    r.raise_for_status()
    return json.dumps(r.json(), ensure_ascii=False)


@mcp.tool()
async def service_status() -> str:
    """后端与 mineru-api 的健康状态。"""
    r = await _request("GET", "/api/system/mineru-health")
    r.raise_for_status()
    return json.dumps(r.json(), ensure_ascii=False)


if __name__ == "__main__":
    # SSE 传输，监听所有网卡，端口 8001。SSE 流端点为 /sse。
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
