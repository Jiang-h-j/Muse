"""探索域 API schema：探索会话响应（AR4 camelCase 边界）。

响应 schema 继承 CamelModel，边界自动 snake_case↔camelCase（如 project_id↔projectId、
updated_at↔updatedAt）。

**无 Request schema（AC2/AC3）**：进入探索接口不接受 body——mode 恒取 project.mode
（后端单一事实源），客户端不传 mode，从数据通道上根除「模式中途切换」。
"""

import uuid

from muse.schemas.base import CamelModel, UTCDateTime


class ExplorationSessionResponse(CamelModel):
    """探索会话响应：进入探索（get-or-create）返回的会话根视图（AC1）。

    边界自动 camelCase：id/projectId/mode/updatedAt。updated_at 经 UTCDateTime
    序列化为带 Z 的 ISO 8601（AR5）。mode 为 guided/free，供前端按 mode 分叉渲染。
    """

    id: uuid.UUID
    project_id: uuid.UUID
    mode: str
    updated_at: UTCDateTime
