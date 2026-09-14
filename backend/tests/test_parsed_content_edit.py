"""Markdown 编辑：换行符归一化与分页结构保护。

这一组用例只依赖纯函数和 Fake 对象，不需要真实数据库。
真实 SQLite / PostgreSQL 的集成与并发用例见 test_parsed_content_edit_db.py。
"""
import pytest

from app.api import parsed as parsed_api
from app.api.parsed import (
    _apply_plain_to_pages,
    _pages_structure_healthy,
    _rebuild_single_page,
    _split_page_sections,
    _sync_pages_markdown,
)
from app.utils.text_normalize import normalize_newlines

# 三页均衡的正常分页产物（LF）
PAGES_LF = "# Page 1\nAAA\nBBB\n# Page 2\nCCC\nDDD\n# Page 3\nEEE\n"
# 编辑后的普通 Markdown：仅把第 2 行 BBB 改成 BBBX
PLAIN_LF = "AAA\nBBBX\nCCC\nDDD\nEEE\n"
# 期望结果：标记位置不变，改动落在第 1 页
EXPECTED = "# Page 1\nAAA\nBBBX\n# Page 2\nCCC\nDDD\n# Page 3\nEEE\n"


def _to(text: str, newline: str) -> str:
    return text.replace("\n", newline)


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


# ---------------- normalize_newlines ----------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("a\r\n\r\nb", "a\n\nb"),
        ("a\nb", "a\nb"),
        ("", ""),
        ("no newline", "no newline"),
    ],
)
def test_normalize_newlines(raw, expected):
    assert normalize_newlines(raw) == expected


def test_normalize_newlines_accepts_none():
    assert normalize_newlines(None) == ""


# ---------------- _apply_plain_to_pages：换行符组合 ----------------

@pytest.mark.parametrize(
    "pages_newline,plain_newline",
    [
        ("\n", "\r\n"),  # 新内容 CRLF、pages LF（线上事故形态）
        ("\r\n", "\n"),  # 反向：pages CRLF、新内容 LF
        ("\r", "\n"),  # 老 Mac 裸 CR
        ("\n", "\r"),
        ("\r\n", "\r\n"),  # 两侧一致，本来就没问题
    ],
)
def test_apply_plain_to_pages_survives_newline_mismatch(pages_newline, plain_newline):
    """两侧换行符不一致时，分页结构必须保持，不能把内容全塞进第 1 页。"""
    result = _apply_plain_to_pages(
        _to(PAGES_LF, pages_newline), _to(PLAIN_LF, plain_newline)
    )
    assert result == EXPECTED


def test_apply_plain_to_pages_handles_mixed_newlines():
    mixed = "AAA\nBBBX\r\nCCC\nDDD\r\nEEE\n"
    assert _apply_plain_to_pages(PAGES_LF, mixed) == EXPECTED


def test_apply_plain_to_pages_output_is_lf_only():
    result = _apply_plain_to_pages(_to(PAGES_LF, "\r\n"), _to(PLAIN_LF, "\r\n"))
    assert "\r" not in result


def test_apply_plain_to_pages_strips_markers_from_plain():
    """防御：普通 Markdown 被历史 bug 污染进 # Page N 标记时，diff 不得把
    这些标记当「新增正文」重复叠加到分页产物里（否则标记会指数级膨胀、
    分页崩溃、PDF↔Markdown 同步失效）。"""
    # 正文与 PLAIN_LF 一致（AAA/BBBX/CCC/DDD/EEE），只是每段前被污染插入了标记
    polluted_plain = "# Page 1\nAAA\nBBBX\n# Page 2\nCCC\nDDD\n# Page 3\nEEE\n"
    result = _apply_plain_to_pages(PAGES_LF, polluted_plain)
    # 标记保持原样（每页一个，不重复），正文改动照常应用
    assert result == EXPECTED
    assert result.count("# Page 1") == 1
    assert result.count("# Page 2") == 1
    assert result.count("# Page 3") == 1


def test_apply_plain_to_pages_regression_without_normalization():
    """锁定回归：不做归一化时确实会退化成「整篇塞进第 1 页」。

    这条用例验证的是归一化为什么必须存在，如果哪天有人把它删掉，这条会先红。
    """
    import difflib

    old_pages = PAGES_LF
    new_plain = _to(PLAIN_LF, "\r\n")
    old_lines = [l for l in old_pages.splitlines(keepends=True)
                 if not parsed_api._is_page_marker_line(l)]
    new_lines = new_plain.splitlines(keepends=True)
    opcodes = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False).get_opcodes()
    # 未归一化时整篇被判成一个 replace —— 这正是事故根因
    assert [op for op in opcodes if op[0] != "equal"] == [("replace", 0, 5, 0, 5)]


# ---------------- 分页结构健康检查 ----------------

def test_pages_structure_healthy_on_normal_document():
    assert _pages_structure_healthy(PAGES_LF) is True


def test_pages_structure_healthy_on_single_page():
    assert _pages_structure_healthy("# Page 1\nAAA\nBBB\n") is True


def test_pages_structure_healthy_on_all_empty_pages():
    assert _pages_structure_healthy("# Page 1\n# Page 2\n") is True


def test_pages_structure_detects_corruption():
    """正文全部集中在首段、后续页为空 —— 换行符事故的典型症状。"""
    corrupted = "# Page 1\nAAA\nBBB\nCCC\nDDD\nEEE\n# Page 2\n# Page 3\n"
    assert _pages_structure_healthy(corrupted) is False


def test_pages_structure_does_not_flag_long_first_page():
    """真实文档里「第一页很长、后续页很短」很常见，不能误判为损坏。"""
    doc = "# Page 1\n" + "X\n" * 200 + "# Page 2\nY\n"
    assert _pages_structure_healthy(doc) is True


def test_split_page_sections_groups_body_under_marker():
    sections = _split_page_sections(PAGES_LF)
    assert [marker for marker, _ in sections] == ["# Page 1", "# Page 2", "# Page 3"]
    assert [len(body) for _, body in sections] == [2, 2, 1]


def test_split_page_sections_handles_leading_content():
    sections = _split_page_sections("Title\n# Page 1\nAAA\n")
    assert [marker for marker, _ in sections] == [None, "# Page 1"]


def test_rebuild_single_page():
    assert _rebuild_single_page("AAA\r\nBBB\r\n") == "# Page 1\n\nAAA\nBBB\n"


def test_rebuild_single_page_on_empty_content():
    assert _rebuild_single_page("") == ""


# ---------------- _sync_pages_markdown ----------------

def _make_file(file_id=7, minio_path="uploads/sample.pdf"):
    return type("F", (), {"id": file_id, "minio_path": minio_path})()


def test_sync_pages_preserves_markers_on_normal_path(monkeypatch):
    fake = _FakeMinio({"sample_pages.md": PAGES_LF})
    monkeypatch.setattr(parsed_api, "minio_client", fake)
    monkeypatch.setattr(parsed_api, "get_buckets", lambda: ("mds",))

    changed = _sync_pages_markdown(_make_file(), PLAIN_LF, old_content=PLAIN_LF.replace("BBBX", "BBB"))

    assert changed is True
    assert fake.puts[("mds", "sample_pages.md")].decode("utf-8") == EXPECTED


def test_sync_pages_degrades_when_structure_corrupted(monkeypatch):
    """结构已损坏时不再盲 diff，降级重建为单页，内容不丢。"""
    corrupted = "# Page 1\nAAA\nBBB\nCCC\n# Page 2\n# Page 3\n"
    fake = _FakeMinio({"sample_pages.md": corrupted})
    monkeypatch.setattr(parsed_api, "minio_client", fake)
    monkeypatch.setattr(parsed_api, "get_buckets", lambda: ("mds",))

    changed = _sync_pages_markdown(_make_file(), "AAA\nBBB\nCCC\n", old_content=" whatever ")

    assert changed is True
    written = fake.puts[("mds", "sample_pages.md")].decode("utf-8")
    assert written == "# Page 1\n\nAAA\nBBB\nCCC\n"
    assert written.count("# Page") == 1


def test_sync_pages_skips_when_object_missing(monkeypatch):
    fake = _FakeMinio({})
    monkeypatch.setattr(parsed_api, "minio_client", fake)
    monkeypatch.setattr(parsed_api, "get_buckets", lambda: ("mds",))

    assert _sync_pages_markdown(_make_file(), PLAIN_LF, old_content="x") is False
    assert fake.puts == {}


def test_sync_pages_noop_when_content_identical(monkeypatch):
    fake = _FakeMinio({"sample_pages.md": PAGES_LF})
    monkeypatch.setattr(parsed_api, "minio_client", fake)
    monkeypatch.setattr(parsed_api, "get_buckets", lambda: ("mds",))

    body = "AAA\nBBB\nCCC\nDDD\nEEE\n"
    assert _sync_pages_markdown(_make_file(), body, old_content=body) is False
    assert fake.puts == {}
