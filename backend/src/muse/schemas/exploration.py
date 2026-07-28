"""探索域 API schema：探索会话响应 + 引导自述理解请求（AR4 camelCase 边界）。

响应 schema 继承 CamelModel，边界自动 snake_case↔camelCase（如 project_id↔projectId、
updated_at↔updatedAt、free_text↔freeText）。

进入探索接口**无 Request schema（AC2/AC3）**：mode 恒取 project.mode（后端单一事实源），
客户端不传 mode，从数据通道上根除「模式中途切换」。引导自述理解接口（Story 2.3 AC4）新增
GuidedInterpretRequest 收当前题干 + 用户一句话自述。
"""

import uuid
from typing import Annotated

from pydantic import StringConstraints

from muse.schemas.base import CamelModel, UTCDateTime

# 非空且有界文本：先 strip，再校验 1 ≤ 长度 ≤ 2000——纯空白（"   "）strip 后为空即 422，
# 兑现 AC4「free_text 空/纯空白 → 422」（仿原型 `if (!answer) return` app.js:456）；
# max_length=2000（review 裁定保守上界）拦超长自述——防单请求塞万字挤爆 prompt / 拖慢流式 /
# 放大记账，超长即 422 挡在建流前，不进 LLM。入库/送 LLM 前已去除首尾空白（送模型的题干/自述干净）。
_NonBlankText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class ExplorationSessionResponse(CamelModel):
    """探索会话响应：进入探索（get-or-create）返回的会话根视图（AC1）。

    边界自动 camelCase：id/projectId/mode/updatedAt。updated_at 经 UTCDateTime
    序列化为带 Z 的 ISO 8601（AR5）。mode 为 guided/free，供前端按 mode 分叉渲染。
    """

    id: uuid.UUID
    project_id: uuid.UUID
    mode: str
    updated_at: UTCDateTime


class GuidedInterpretRequest(CamelModel):
    """引导自述理解请求（Story 2.3 AC4）：当前题干 + 用户一句话自述。

    边界 camelCase：question / freeText。V1 题库是前端常量（app.js:5-62），端点收 question
    文本即可、后端不镜像题库（受控决策，见 story Dev Notes）。二者均 _NonBlankText：空/纯空白
    → 422（question 为渲染题时的题干、freeText 为用户自述，皆不应为空）。
    """

    question: _NonBlankText
    free_text: _NonBlankText
