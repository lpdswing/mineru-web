import pytest

from app.services import file_parser_worker as worker


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 1),
        ("", 1),
        ("0", 1),
        ("-2", 1),
        ("abc", 1),
        ("3", 3),
    ],
)
def test_parse_worker_concurrency_defaults_to_one_for_invalid_values(raw, expected):
    assert worker.parse_worker_concurrency(raw) == expected
