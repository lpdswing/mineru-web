"""Markdown 文本换行符归一化。

为什么需要这一层：
`_apply_plain_to_pages` 用 `splitlines(keepends=True)` 做行级 diff，行内容包含
行尾的换行符。一旦新旧两侧换行符不一致（一侧 CRLF、一侧 LF），SequenceMatcher
会把每一行都判为不相等，退化成「整篇 replace」——把所有新内容插到第一个
`# Page N` 之后，第 2 页起全部变空，且**不可自愈**。

规则很简单：统一成 LF。Markdown 语义不受影响，但行级 diff 依赖它。

放在 utils 而不是 api 层，是为了让 services（parser / artifact_sync）也能引用，
避免 services → api 的反向依赖。
"""

from __future__ import annotations

_LF = "\n"


def normalize_newlines(text: str | None) -> str:
    """把 CRLF / CR 统一成 LF；None 视为空串。

    - `"a\\r\\nb"` -> `"a\\nb"`
    - `"a\\rb"`   -> `"a\\nb"`
    - `"a\\r\\n\\r\\nb"` -> `"a\\n\\nb"`（空行结构保留）
    """
    if not text:
        return ""
    # 先折 CRLF 再折裸 CR，顺序不能反（否则 \r\n 会先变成 \n\n）
    return text.replace("\r\n", _LF).replace("\r", _LF)
