"""作品域 API schema：创建/列表（AR4 camelCase 边界）。

请求/响应 schema 继承 CamelModel，边界自动 snake_case↔camelCase（如 updated_at↔updatedAt）。
mode 用 Literal 在边界枚举校验；title 可空——前端可留空提交，service 侧回落「未命名小说」，
故此处不设 min_length（否则会 422 拒绝合法的留空提交）。
"""

import uuid
from typing import Literal

from pydantic import Field

from muse.schemas.base import CamelModel, UTCDateTime

# 标题列宽对齐 models.project.Project.title（String(255)）；给上界防超大输入。
_TITLE_MAX_LENGTH = 255


class ProjectCreateRequest(CamelModel):
    """新建作品入参（AC1）。

    mode 必填且仅接受 guided/free（原型两步弹窗第一步的选择，app.js:354-355）。
    title 可选：留空/纯空白由 service `strip` 后回落「未命名小说」（原型 app.js:1745-1746）。
    不设 min_length（留空是合法提交，不应 422）；设 max_length 防超列宽输入。
    """

    mode: Literal["guided", "free"]
    title: str | None = Field(default=None, max_length=_TITLE_MAX_LENGTH)


class ProjectResponse(CamelModel):
    """作品响应：列表/创建共用的安全视图（AC1/AC2）。

    边界自动 camelCase：id/title/mode/phase/updatedAt。updated_at 经 UTCDateTime
    序列化为带 Z 的 ISO 8601（前端据此格式化「今天 16:40」等相对时间）。
    """

    id: uuid.UUID
    title: str
    mode: str
    phase: str
    updated_at: UTCDateTime
