import json

from app.services.popo import (
    PopoConfig,
    PopoPostprocessor,
    build_popo_outputs,
    discover_popo_artifacts,
    parse_popo_enabled,
)


def test_parse_popo_enabled_accepts_common_truthy_values():
    assert parse_popo_enabled("1") is True
    assert parse_popo_enabled("true") is True
    assert parse_popo_enabled("yes") is True
    assert parse_popo_enabled("0") is False
    assert parse_popo_enabled("") is False
    assert parse_popo_enabled(None) is False


def test_discover_popo_artifacts_finds_mineru_json_outputs():
    artifacts = discover_popo_artifacts(
        [
            "sample/auto/sample_middle.json",
            "sample/auto/sample_content_list.json",
            "sample/auto/sample_model.json",
            "sample/images/a.png",
        ]
    )

    assert artifacts == {
        "middle_json": "sample/auto/sample_middle.json",
        "content_list_json": "sample/auto/sample_content_list.json",
        "model_json": "sample/auto/sample_model.json",
    }


def test_build_popo_outputs_uses_export_level_paths():
    assert build_popo_outputs("sample") == {
        "markdown": "sample_popo.md",
        "json": "sample_popo.json",
        "status": "sample_popo_status.json",
    }


class FakeMinio:
    def __init__(self):
        self.objects = {}

    def put_object(self, bucket, path, data, length, content_type=None):
        self.objects[(bucket, path)] = {
            "content": data.read(),
            "content_type": content_type,
        }


def test_write_status_uploads_json_status():
    fake_minio = FakeMinio()
    postprocessor = PopoPostprocessor(
        config=PopoConfig(enabled=True, api_url="http://popo:8010", timeout_seconds=10),
        minio=fake_minio,
    )

    postprocessor.write_status("mds", "sample_popo_status.json", "skipped", "missing model")

    payload = json.loads(fake_minio.objects[("mds", "sample_popo_status.json")]["content"])
    assert payload["status"] == "skipped"
    assert payload["message"] == "missing model"
    assert fake_minio.objects[("mds", "sample_popo_status.json")]["content_type"] == "application/json"
