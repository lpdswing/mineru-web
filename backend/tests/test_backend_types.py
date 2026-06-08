from app.models.enums import (
    BackendType,
    SettingsBackendType,
    normalize_backend_value,
    validate_mineru_backend,
)


def test_settings_backend_type_supports_mineru_api_backends():
    assert {item.value for item in SettingsBackendType} == {
        "pipeline",
        "vlm-auto-engine",
        "vlm-http-client",
        "hybrid-auto-engine",
        "hybrid-http-client",
    }


def test_settings_backend_maps_to_file_backend_without_losing_specific_value():
    assert SettingsBackendType.PIPELINE.to_file_backend() == BackendType.PIPELINE
    assert SettingsBackendType.VLM_AUTO_ENGINE.to_file_backend() == BackendType.VLM_AUTO_ENGINE
    assert SettingsBackendType.VLM_HTTP_CLIENT.to_file_backend() == BackendType.VLM_HTTP_CLIENT
    assert SettingsBackendType.HYBRID_AUTO_ENGINE.to_file_backend() == BackendType.HYBRID_AUTO_ENGINE
    assert SettingsBackendType.HYBRID_HTTP_CLIENT.to_file_backend() == BackendType.HYBRID_HTTP_CLIENT


def test_backend_normalization_keeps_mineru_prefix_backends_compatible():
    assert normalize_backend_value("VLM_SGLANG_CLIENT") == "vlm-http-client"
    assert validate_mineru_backend("vlm-vllm-engine") == "vlm-vllm-engine"
    assert validate_mineru_backend("hybrid-vllm-async-engine") == "hybrid-vllm-async-engine"
