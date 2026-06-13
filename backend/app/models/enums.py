"""
统一的枚举定义
避免在多个模块中重复定义枚举类型
"""
import enum


class FileStatus(enum.Enum):
    """文件解析状态"""
    PENDING = 'pending'
    PARSING = 'parsing'
    PARSED = 'parsed'
    PARSE_FAILED = 'parse_failed'


class BackendType(enum.Enum):
    """解析后端类型（用于 File 模型）"""
    PIPELINE = 'pipeline'
    VLM_AUTO_ENGINE = 'vlm-auto-engine'
    VLM_HTTP_CLIENT = 'vlm-http-client'
    HYBRID_AUTO_ENGINE = 'hybrid-auto-engine'
    HYBRID_HTTP_CLIENT = 'hybrid-http-client'
    # Legacy category values kept readable for existing rows.
    VLM = 'vlm'
    HYBRID = 'hybrid'


class SettingsBackendType(enum.Enum):
    """设置中的后端类型（更详细的配置）"""
    PIPELINE = 'pipeline'
    VLM_AUTO_ENGINE = 'vlm-auto-engine'
    VLM_HTTP_CLIENT = 'vlm-http-client'
    HYBRID_AUTO_ENGINE = 'hybrid-auto-engine'
    HYBRID_HTTP_CLIENT = 'hybrid-http-client'

    def to_file_backend(self) -> BackendType:
        """转换为文件后端类型"""
        if self == SettingsBackendType.PIPELINE:
            return BackendType.PIPELINE
        if self == SettingsBackendType.VLM_AUTO_ENGINE:
            return BackendType.VLM_AUTO_ENGINE
        if self == SettingsBackendType.VLM_HTTP_CLIENT:
            return BackendType.VLM_HTTP_CLIENT
        if self == SettingsBackendType.HYBRID_AUTO_ENGINE:
            return BackendType.HYBRID_AUTO_ENGINE
        return BackendType.HYBRID_HTTP_CLIENT


DEFAULT_MINERU_BACKEND = BackendType.PIPELINE.value

OFFICIAL_MINERU_BACKENDS = (
    BackendType.PIPELINE.value,
    BackendType.VLM_AUTO_ENGINE.value,
    BackendType.VLM_HTTP_CLIENT.value,
    BackendType.HYBRID_AUTO_ENGINE.value,
    BackendType.HYBRID_HTTP_CLIENT.value,
)

LEGACY_BACKEND_ALIASES = {
    "PIPELINE": BackendType.PIPELINE.value,
    "VLM": BackendType.VLM.value,
    "HYBRID": BackendType.HYBRID.value,
    "VLM_TRANSFORMERS": BackendType.VLM_AUTO_ENGINE.value,
    "VLM_SGLANG_ENGINE": BackendType.VLM_AUTO_ENGINE.value,
    "VLM_SGLANG_CLIENT": BackendType.VLM_HTTP_CLIENT.value,
    "VLM_AUTO_ENGINE": BackendType.VLM_AUTO_ENGINE.value,
    "VLM_HTTP_CLIENT": BackendType.VLM_HTTP_CLIENT.value,
    "HYBRID_AUTO_ENGINE": BackendType.HYBRID_AUTO_ENGINE.value,
    "HYBRID_HTTP_CLIENT": BackendType.HYBRID_HTTP_CLIENT.value,
}


def normalize_backend_value(value, default: str = DEFAULT_MINERU_BACKEND) -> str:
    if value is None:
        return default
    if isinstance(value, enum.Enum):
        value = value.value
    value = str(value)
    return LEGACY_BACKEND_ALIASES.get(value, value)


def is_mineru_backend_supported(value) -> bool:
    backend = normalize_backend_value(value, default="")
    return (
        backend == BackendType.PIPELINE.value
        or backend.startswith("vlm-")
        or backend.startswith("hybrid-")
    )


def validate_mineru_backend(value) -> str:
    backend = normalize_backend_value(value)
    if not is_mineru_backend_supported(backend):
        raise ValueError(backend)
    return backend
