"""探索域 API schema：探索会话响应 + 引导自述理解请求（AR4 camelCase 边界）。

响应 schema 继承 CamelModel，边界自动 snake_case↔camelCase（如 project_id↔projectId、
updated_at↔updatedAt、free_text↔freeText）。

进入探索接口**无 Request schema（AC2/AC3）**：mode 恒取 project.mode（后端单一事实源），
客户端不传 mode，从数据通道上根除「模式中途切换」。引导自述理解接口（Story 2.3 AC4）新增
GuidedInterpretRequest 收当前题干 + 用户一句话自述。
"""

import uuid
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_serializer
from pydantic.alias_generators import to_camel

from muse.schemas.base import CamelModel, UTCDateTime

# 非空且有界文本：先 strip，再校验 1 ≤ 长度 ≤ 2000——纯空白（"   "）strip 后为空即 422，
# 兑现 AC4「free_text 空/纯空白 → 422」（仿原型 `if (!answer) return` app.js:456）；
# max_length=2000（review 裁定保守上界）拦超长自述——防单请求塞万字挤爆 prompt / 拖慢流式 /
# 放大记账，超长即 422 挡在建流前，不进 LLM。入库/送 LLM 前已去除首尾空白（送模型的题干/自述干净）。
_NonBlankText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]

# 可空但有界文本：允许空串（min_length=0），仅设长度上界——用于线索 value（空串=前端「尚未
# 确定」占位），拦超长内容（单请求塞 1MB value 落库 TEXT、后续被整理端点塞进 prompt 挤爆
# max_tokens），超长即 422 挡在入库前。max_length 与 _NonBlankText 同取保守上界 2000。
_BoundedText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2000)
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


class GuidedAnswerRequest(CamelModel):
    """引导答案保存请求（Story 2.4 AC5）：某题位的一句话答案 + 作答路径。

    边界 camelCase：questionIndex / question / answer / answerType。question_index 非负
    （ge=0）——不硬编码上界 6（延续「后端不镜像题库」精神，题数是前端知识；脏 index 由前端
    契约保证，唯一约束 + 至多几条孤儿记录无严重后果）。但须加 int4 上界（lt=2**31）：DB
    question_index 是 PG int4，超上界值会在 INSERT 时抛 DataError（未注册专用 handler → 落
    通用 Exception → 500），加界后由 pydantic 拦成 422，把「脏 index」统一收敛到入参校验层而非
    DB 层。question/answer 复用 _NonBlankText（strip + 1≤len≤2000，空/纯空白/超长 → 422）；
    answer_type 用 Literal 限定，非法值自动 422。
    """

    question_index: int = Field(ge=0, lt=2**31)
    question: _NonBlankText
    answer: _NonBlankText
    answer_type: Literal["option", "custom"]


class GuidedAnswerResponse(CamelModel):
    """引导答案资源视图（Story 2.4 AC5）：保存后回传 + 恢复列表元素。

    边界自动 camelCase：id/questionIndex/question/answer/answerType/updatedAt。updated_at 经
    UTCDateTime 序列化为带 Z 的 ISO 8601（AR5）。GET 列表端点返回 list[GuidedAnswerResponse]。
    """

    id: uuid.UUID
    question_index: int
    question: str
    answer: str
    answer_type: str
    updated_at: UTCDateTime


class FreeMessageRequest(CamelModel):
    """自由对话消息请求（Story 2.6 AC2）：用户发送的一条消息正文。

    边界 camelCase：content。复用既有 _NonBlankText（strip + 1≤len≤2000，空/纯空白/超长 → 422）。
    """

    content: _NonBlankText


class FreeMessageResponse(CamelModel):
    """自由对话消息资源视图（Story 2.6 AC6）：恢复列表元素。

    边界自动 camelCase：id/role/content/createdAt。对话是追加式流，用创建时间排序展示，不像
    引导答案那样有"更新时间"语义，故用 created_at 而非 updated_at。
    """

    id: uuid.UUID
    role: str
    content: str
    created_at: UTCDateTime


class ClueResponse(CamelModel):
    """故事线索资源视图（Story 2.6 AC3/AC5/AC6）：预设槙位或自定义线索的统一响应形态。

    边界自动 camelCase：id/clueKey/kind/label/value/userEdited/displayOrder/updatedAt。
    clue_key 仅 preset 有值，custom 恒 None。
    """

    id: uuid.UUID
    clue_key: str | None
    kind: str
    label: str
    value: str
    user_edited: bool
    display_order: int
    updated_at: UTCDateTime


class ClueEditRequest(CamelModel):
    """线索编辑请求（Story 2.6 AC3/AC5）：编辑后置 user_edited=true。

    边界 camelCase：value/label。value 用 `_BoundedText`（允许空串=清空为「尚未确定」，占位
    逻辑在前端；但设长度上界拦超长内容——防单请求塞 1MB value 挤爆整理端点 prompt）；
    label 用 `_NonBlankText | None`（**不可用裸 `str | None`**——会绕开创建路径
    ClueCreateRequest.label 的非空约束，允许把线索改名为空字符串）：不提供（None）则不改名，
    提供则必须非空有界，不因 kind 强制拒绝（统一代码路径，YAGNI）。
    """

    value: _BoundedText
    label: _NonBlankText | None = None


class ClueCreateRequest(CamelModel):
    """自定义线索新增请求（Story 2.6 AC3）：边界 camelCase：label/value。value 用 `_BoundedText`
    （允许空串，设长度上界拦超长，同 ClueEditRequest）。"""

    label: _NonBlankText
    value: _BoundedText = ""


class GuidanceStartRequest(CamelModel):
    """自由探索零对话四入口请求（Story 2.8 AC3）：边界 camelCase：entry。

    四个固定产品入口标识，`Literal` 约束非法值 422（同 `project.mode`/`answer_type`
    既有 `Literal` 用法）。取值语义见 `guidance_agent._ENTRY_FIELD_MAP`。
    """

    entry: Literal["story_idea", "protagonist", "conflict", "world"]


class GuidanceStateResponse(CamelModel):
    """自由探索导航状态响应（Story 2.8 AC1/AC2/AC3/AC6/AC7）：完成度 + 当前问题 + 就绪位。

    边界自动 camelCase：currentField/currentQuestion/readyToSettle。**`fields` 是例外**
    ——`alias_generator=to_camel` 只作用于模型字段名，不转换 dict 值内部的 key（已用脚本
    验证 Pydantic 行为）。内部（`guidance_state.fields`）仍用 snake_case 存储（与
    `story_settle_agent._BACKBONE_FIELDS`/`story_bible` 列名一致，不打破项目既定的「内部
    snake_case、边界 camelCase」约定），只在本响应序列化时经 `field_serializer` 把 dict
    key 转 camelCase（如 `core_appeal` → `coreAppeal`），供前端拿到与其他字段一致的
    camelCase key。`current_field`（若非空）也是 snake_case 领域值，同样需要转换。
    """

    fields: dict[str, str]
    current_field: str | None
    current_question: str | None
    ready_to_settle: bool

    @field_serializer("fields")
    def _camel_fields(self, value: dict[str, str]) -> dict[str, str]:
        return {to_camel(key): status for key, status in value.items()}

    @field_serializer("current_field")
    def _camel_current_field(self, value: str | None) -> str | None:
        return to_camel(value) if value is not None else None


class GuidanceSuggestionsResponse(CamelModel):
    """按需回答思路响应（Story 2.8 AC4）：边界 camelCase：suggestions（无内部 key 转换需要
    ——`list[str]` 是纯文本数组，非 dict）。"""

    suggestions: list[str]

