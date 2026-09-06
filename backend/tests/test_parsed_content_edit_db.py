"""Markdown 编辑：真实数据库集成测试（SQLite + PostgreSQL 双跑）。

纯函数的用例在 test_parsed_content_edit.py，这里只验证涉及数据库写路径的行为：
- 换行符在两种库上都归一化成 LF
- 版本记录的生成/去重
- 加锁时机（PG 有行锁，SQLite 静默降级）

PG 用例默认读 backend/.env 里的 DATABASE_URL；连不上时自动跳过，不会让本地单测变红。
"""
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import parsed as parsed_api
from app.api.parsed import _commit_new_version, _lock_versioned_file
from app.database import get_db
from app.models.base import Base
from app.models.enums import FileStatus
from app.models.file import File as FileModel
from app.models.folder import Folder  # noqa: F401  files.folder_id 的外键依赖
from app.models.parsed_content import ParsedContent
from app.models.parsed_content_version import ParsedContentVersion
from app.utils.text_normalize import normalize_newlines
from main import app as fastapi_app

USER_ID = "u-integration"
FILENAME = "sample.pdf"


def _pg_url() -> str | None:
    """优先用环境变量，其次读 backend/.env 里的 DATABASE_URL。"""
    url = os.getenv("TEST_PG_URL")
    if url:
        return url
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("DATABASE_URL="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _db_urls() -> list[tuple[str, str]]:
    urls = [("sqlite", "sqlite+pysqlite:///:memory:")]
    pg = _pg_url()
    if pg:
        urls.append(("postgresql", pg))
    return urls


def _make_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine(url, pool_pre_ping=True)


@contextmanager
def _isolated_session(engine):
    """用外部事务 + savepoint 隔离：被测代码的 commit() 只释放 savepoint，
    测试结束整体 rollback，不会在真实库上留下数据。
    """
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


def _seed(session: Session, content: str, status=FileStatus.PARSED):
    record = FileModel(
        user_id=USER_ID,
        filename=FILENAME,
        size=1024,
        status=status,
        minio_path=f"uploads/{FILENAME}",
        content_type="application/pdf",
    )
    session.add(record)
    session.flush()
    session.add(ParsedContent(user_id=USER_ID, file_id=record.id, content=content))
    session.commit()
    return record.id


class _FakeObject:
    def __init__(self, content):
        self.content = content

    def read(self):
        return self.content

    def close(self):
        pass

    def release_conn(self):
        pass


class _FakeMinio:
    def __init__(self, objects=None):
        self.objects = {("mds", k): v.encode("utf-8") for k, v in (objects or {}).items()}
        self.puts: dict[tuple[str, str], bytes] = {}

    def get_object(self, bucket, path):
        if (bucket, path) not in self.objects:
            raise FileNotFoundError(path)
        return _FakeObject(self.objects[(bucket, path)])

    def put_object(self, bucket, path, data, length, content_type=None):
        self.puts[(bucket, path)] = data.read()


@pytest.fixture(params=_db_urls(), ids=[name for name, _ in _db_urls()])
def db_env(request, monkeypatch):
    name, url = request.param
    engine = _make_engine(url)
    try:
        Base.metadata.create_all(engine)
    except Exception as exc:  # PG 连不上时跳过，而不是让单测变红
        engine.dispose()
        pytest.skip(f"{name} 不可用: {exc}")

    fake_minio = _FakeMinio({"sample_pages.md": "# Page 1\nAAA\nBBB\n"})
    monkeypatch.setattr(parsed_api, "minio_client", fake_minio)
    monkeypatch.setattr(parsed_api, "get_buckets", lambda: ("mds",))

    with _isolated_session(engine) as session:
        fastapi_app.dependency_overrides[get_db] = lambda: session
        try:
            yield name, session, fake_minio
        finally:
            fastapi_app.dependency_overrides.pop(get_db, None)
    engine.dispose()


# ---------------- 换行符归一化（两种库一致） ----------------

def test_save_crlf_content_is_normalized_in_db(db_env):
    _, session, _ = db_env
    file_id = _seed(session, "AAA\nBBB\n")

    result = _commit_new_version(session, file_id, USER_ID, "AAA\r\nBBB\r\n", "save", None)

    assert result.applied_content == "AAA\nBBB\n"
    stored = session.query(ParsedContent).filter(
        ParsedContent.file_id == file_id
    ).first()
    assert stored.content == "AAA\nBBB\n"
    assert "\r" not in stored.content


def test_save_endpoint_stores_lf_content(db_env):
    name, session, _ = db_env
    file_id = _seed(session, "AAA\n")
    client = TestClient(fastapi_app)

    response = client.put(
        f"/api/files/{file_id}/parsed_content",
        json={"content": "AAA\r\nBBB\r\n"},
        headers={"X-User-Id": USER_ID},
    )

    assert response.status_code == 200, response.text
    stored = session.query(ParsedContent).filter(
        ParsedContent.file_id == file_id
    ).first()
    assert stored.content == "AAA\nBBB\n"


def test_save_crlf_only_change_does_not_create_version(db_env):
    """只有换行符不同不算内容变化，否则历史里会多出一条冗余快照。"""
    _, session, _ = db_env
    file_id = _seed(session, "AAA\nBBB\n")

    result = _commit_new_version(session, file_id, USER_ID, "AAA\r\nBBB\r\n", "save", None)

    assert result.new_version == 0
    versions = session.query(ParsedContentVersion).filter(
        ParsedContentVersion.file_id == file_id
    ).all()
    # 只有惰性补建的 v1
    assert [v.version for v in versions] == [1]


def test_save_real_change_creates_version(db_env):
    _, session, _ = db_env
    file_id = _seed(session, "AAA\nBBB\n")

    result = _commit_new_version(session, file_id, USER_ID, "AAA\nBBB\nCCC\n", "save", "note")

    assert result.new_version == 2
    assert result.old_content == "AAA\nBBB\n"
    assert result.applied_content == "AAA\nBBB\nCCC\n"


def test_save_twice_identical_content_creates_single_version(db_env):
    """连续两次保存相同内容，第二次必须判定为无变化。"""
    _, session, _ = db_env
    file_id = _seed(session, "AAA\nBBB\n")

    first = _commit_new_version(session, file_id, USER_ID, "NEW\n", "save", None)
    second = _commit_new_version(session, file_id, USER_ID, "NEW\n", "save", None)

    assert first.new_version == 2
    assert second.new_version == 0
    versions = session.query(ParsedContentVersion.version).filter(
        ParsedContentVersion.file_id == file_id
    ).all()
    assert sorted(v[0] for v in versions) == [1, 2]


def test_restore_crlf_history_version_writes_lf(db_env):
    """恢复一条被 CRLF 污染过的历史版本，落库内容必须是 LF。"""
    _, session, _ = db_env
    file_id = _seed(session, "AAA\nBBB\n")
    session.add(
        ParsedContentVersion(
            user_id=USER_ID, file_id=file_id, version=2,
            content="OLD\r\nTEXT\r\n", source="save",
        )
    )
    session.commit()
    target = session.query(ParsedContentVersion).filter(
        ParsedContentVersion.file_id == file_id,
        ParsedContentVersion.version == 2,
    ).first()

    result = _commit_new_version(
        session, file_id, USER_ID, target.content, "restore", "恢复自 v2"
    )

    assert result.applied_content == "OLD\nTEXT\n"
    stored = session.query(ParsedContent).filter(
        ParsedContent.file_id == file_id
    ).first()
    assert stored.content == "OLD\nTEXT\n"
    assert "\r" not in stored.content


def test_versions_endpoint_returns_versions(db_env):
    name, session, _ = db_env
    file_id = _seed(session, "AAA\n")
    _commit_new_version(session, file_id, USER_ID, "BBB\n", "save", None)
    client = TestClient(fastapi_app)

    response = client.get(
        f"/api/files/{file_id}/parsed_content/versions",
        headers={"X-User-Id": USER_ID},
    )

    assert response.status_code == 200, response.text
    versions = response.json()
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["is_current"] is True


# ---------------- 加锁：SQLite 降级、PG 行锁 ----------------

def test_with_for_update_is_silent_on_sqlite(db_env):
    """SQLite 的 dialect 会静默忽略 FOR UPDATE，加锁路径必须照常工作。"""
    name, session, _ = db_env
    file_id = _seed(session, "AAA\n")

    file, pc = _lock_versioned_file(session, file_id, USER_ID)

    assert file.id == file_id
    assert pc.content == "AAA\n"


def test_lock_rejects_unparsed_file(db_env):
    from fastapi import HTTPException

    _, session, _ = db_env
    file_id = _seed(session, "AAA\n", status=FileStatus.PENDING)

    with pytest.raises(HTTPException) as exc:
        _lock_versioned_file(session, file_id, USER_ID)

    assert exc.value.status_code == 400


def test_concurrent_commit_reads_fresh_content_after_lock(monkeypatch):
    """锁的语义：后到的事务必须读到先到事务已提交的内容，而不是加锁前的快照。

    需要真实提交的数据可见性，因此不能用 db_env 的 savepoint 隔离（外层事务未提交，
    其他连接看不到种子数据）。这里直接连 PG、真正提交一条测试数据，测完按外键顺序清理。
    SQLite 没有行锁，跳过。
    """
    pg = _pg_url()
    if not pg or not pg.startswith("postgresql"):
        pytest.skip("需要 PostgreSQL 才能验证行锁语义")

    CONC_USER = "u-concurrency"
    engine = _make_engine(pg)
    Base.metadata.create_all(engine)

    fake_minio = _FakeMinio({})
    monkeypatch.setattr(parsed_api, "minio_client", fake_minio)
    monkeypatch.setattr(parsed_api, "get_buckets", lambda: ("mds",))

    file_id: int | None = None
    try:
        seed = Session(bind=engine)
        record = FileModel(
            user_id=CONC_USER,
            filename="conc.pdf",
            size=1,
            status=FileStatus.PARSED,
            minio_path="uploads/conc.pdf",
            content_type="application/pdf",
        )
        seed.add(record)
        seed.flush()
        file_id = record.id
        seed.add(ParsedContent(user_id=CONC_USER, file_id=file_id, content="ORIGINAL\n"))
        seed.commit()  # 真正提交，让其他连接可见
        seed.close()

        session_a = Session(bind=engine)
        try:
            _, pc_a = _lock_versioned_file(session_a, file_id, CONC_USER)
            pc_a.content = "FROM_A\n"
            session_a.flush()  # 持有行锁，不提交

            box: dict[str, object] = {}

            def worker_b():
                session_b = Session(bind=engine)
                try:
                    box["result"] = _commit_new_version(
                        session_b, file_id, CONC_USER, "FROM_B\n", "save", None
                    )
                except Exception as exc:  # pragma: no cover - 仅失败时记录
                    box["error"] = exc
                finally:
                    session_b.close()

            thread = threading.Thread(target=worker_b)
            thread.start()
            time.sleep(0.8)  # 确保 B 已阻塞在行锁上
            session_a.commit()  # 释放锁
            thread.join(timeout=15)
        finally:
            session_a.close()

        assert "error" not in box, box.get("error")
        result = box["result"]
        assert result.old_content == "FROM_A\n"      # 不是加锁前的 ORIGINAL
        assert result.applied_content == "FROM_B\n"
        assert result.new_version == 2               # v1(惰性) + v2，没有重复版本
    finally:
        if file_id is not None:
            cleanup = Session(bind=engine)
            try:
                cleanup.query(ParsedContentVersion).filter(
                    ParsedContentVersion.user_id == CONC_USER
                ).delete(synchronize_session=False)
                cleanup.query(ParsedContent).filter(
                    ParsedContent.user_id == CONC_USER
                ).delete(synchronize_session=False)
                cleanup.query(FileModel).filter(
                    FileModel.user_id == CONC_USER
                ).delete(synchronize_session=False)
                cleanup.commit()
            finally:
                cleanup.close()
        engine.dispose()
