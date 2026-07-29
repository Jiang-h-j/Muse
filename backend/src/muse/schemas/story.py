"""故事设定域 API schema：文风锚点抽取（3.2）、12 字段候选卡（3.3）、编辑/反馈升版本（3.4）。

响应/请求继承 CamelModel，边界自动 snake_case↔camelCase（如 sample_id↔sampleId、
style_profile↔styleProfile、changed_fields↔changedFields）。确认（3.5）的 schema 后续按需扩。
"""

from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from muse.schemas.base import CamelModel

# 粘贴样本：非空且有界。min_length=20 对齐原型 paste 门槛「至少 20 字」（app.js:2238-2239）——
# 太短抽不出可靠文风；max_length=4000 保守上界，拦超长样本挤爆 prompt / 拖慢抽取 / 放大记账，
# 超长即 422 挡在建流前不进 LLM（同 exploration._NonBlankText 的超长防护思路，样本比自述更长
# 故上界放宽到 4000）。strip 去首尾空白后再校验长度。
_SampleText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=20, max_length=4000)
]


class StyleAnchorRequest(CamelModel):
    """文风锚点抽取请求（AC1）：两种锚定方式二选一——库选 sampleId 或粘贴 sampleText。

    边界 camelCase：sampleId / sampleText。二者**互斥且至少其一**（model_validator 校验）：
    - 库选：只传 sampleId（预置样本原文后端持有，不必把整段原文经网络回传）。
    - 粘贴：只传 sampleText（用户自带范文）。
    service 层 resolve_sample_text 把二者统一解析为待抽取原文，契约仍单一（story 决策）。
    """

    sample_id: str | None = Field(default=None, max_length=64)
    sample_text: _SampleText | None = None

    @model_validator(mode="after")
    def _exactly_one_anchor(self) -> "StyleAnchorRequest":
        """恰有一个锚定来源：都给或都不给都 422（避免二义/空请求进抽取链）。"""
        has_id = self.sample_id is not None and self.sample_id.strip() != ""
        has_text = self.sample_text is not None
        if has_id == has_text:
            raise ValueError("sampleId 与 sampleText 须恰好提供一个")
        # 归一化 sample_id：有值时去首尾空白（否则「 cold-rain 」查库命中不了、误 400）；
        # 空白/未提供统一清成 None，便于 service 落到 sample_text 分支。
        self.sample_id = self.sample_id.strip() if has_id else None
        return self


class StyleProfileResponse(CamelModel):
    """文风锚点抽取响应（AC2/AC5）：抽取后的 style_profile 文本 + 是否已锚定。

    边界 camelCase：styleProfile / anchored。style_profile 为五维「标签：内容」多行文本
    （V1 存 Text，story 待确认项 1）；anchored 恒 true（本端点成功即已锚定，未锚定态由前端
    不调用本端点表达——AC5 的「可空/默认风格」是 story_bible.style_profile 为 NULL 的读取侧
    语义，不经本响应表达）。
    """

    style_profile: str
    anchored: bool = True


class StyleSampleResponse(CamelModel):
    """预置样本库一项（GET samples，AC1）：供前端渲染样本卡片。

    边界 camelCase：id/name/note/excerpt。不含完整原文 text（抽取用原文后端内部持有，库选
    只需回传 sampleId；避免整段原文无谓下发）。
    """

    id: str
    name: str
    note: str
    excerpt: str


class StoryProfileCard(CamelModel):
    """12 字段故事设定候选卡（Story 3.3，FR12）：探索凝练产物的数据契约。

    边界 camelCase（如 core_appeal↔coreAppeal、style_profile↔styleProfile）。是 3.4 编辑/
    3.5 确认/前端弹卡渲染消费候选卡的**单一契约**。字段对齐 story_bible 12 列与 [[project_
    muse_setting_fields]] 的 ①-⑫ 编号：
    - 主干 7（`str`，缺料为空串，对齐 story_bible 主干列 server_default="" 语义）。
    - 题材特化 4（`str | None`，按 genre 激活、不匹配为 None，对齐 story_bible 特化列 NULL）。
    - ⑫ style_profile（`str | None`，读 3.2 抽取值，未锚定为 None）。

    本 story emit-only：候选卡经 worker SSE result 返回、**不落 story_bible**（持久化归 3.4/
    3.5）。revision/变化项是 3.4 待确认卡持久化的概念，不在本 schema（故无 revision 字段）。
    """

    # 通用主干 7（必填语义，缺料空串）
    genre: str
    core_appeal: str
    protagonist: str
    main_conflict: str
    world_rules: str
    overall_tone: str
    opening_hook: str
    # 题材特化 4（按 genre 激活，不匹配 None）
    power_system: str | None = None
    golden_finger: str | None = None
    romance_line: str | None = None
    faction_landscape: str | None = None
    # Muse 独有 1（读 3.2 style_profile，未锚定 None）
    style_profile: str | None = None


class StoryProfileCardResponse(CamelModel):
    """候选卡完整响应（Story 3.4）：12 内容字段 + 状态位（revision/changedFields/status）。

    编辑（PATCH）/反馈升版本（POST revise）/恢复（GET）三端点的统一响应契约，直接从
    story_bible ORM 行序列化（CamelModel from_attributes=True）。边界 camelCase（如
    coreAppeal / styleProfile / changedFields）。

    与 StoryProfileCard（3.3 SSE emit 纯契约）区别：本类多带 revision/changed_fields/status
    状态位——它们是 3.4 落库后才有的概念，故独立成 response 类、不污染 3.3 的 emit 契约
    （worker SSE result 仍用 StoryProfileCard，零改动、3.3 测试零回归）。
    """

    # 12 内容字段（同 StoryProfileCard）
    genre: str
    core_appeal: str
    protagonist: str
    main_conflict: str
    world_rules: str
    overall_tone: str
    opening_hook: str
    power_system: str | None = None
    golden_finger: str | None = None
    romance_line: str | None = None
    faction_landscape: str | None = None
    style_profile: str | None = None
    # 状态位（3.4）
    revision: int
    changed_fields: list[str] | None = None
    status: str


class ProfileFeedbackRequest(CamelModel):
    """反馈升版本请求（Story 3.4 AC3）：用户「你想调整什么？」的反馈文本。

    边界 camelCase：feedback。非空有界——min_length=1（非空，strip 后）拦空反馈（原型
    app.js:684 空反馈 return 不提交）；max_length 保守上界拦超长挤爆重凝练 prompt，超长即
    422 挡在进 LLM 前（同 _SampleText 超长防护思路）。
    """

    feedback: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]


class ProfileCardEditRequest(CamelModel):
    """直接编辑候选卡请求（Story 3.4 AC2）：12 内容字段全可选，只改传入的字段值。

    边界 camelCase（coreAppeal 等）。全字段 `str | None`（默认 None=不改该字段）——model 只
    暴露 12 内容字段、不含 status/revision/changedFields，天然防越权改状态位（受控决策 3）。
    service 侧 update_card_fields 仅对非 None 字段写值、revision 不变。允许编辑 style_profile
    文本（原型第⑫字段亦 contenteditable，story 待确认项 5）。
    """

    genre: str | None = None
    core_appeal: str | None = None
    protagonist: str | None = None
    main_conflict: str | None = None
    world_rules: str | None = None
    overall_tone: str | None = None
    opening_hook: str | None = None
    power_system: str | None = None
    golden_finger: str | None = None
    romance_line: str | None = None
    faction_landscape: str | None = None
    style_profile: str | None = None

    def to_fields(self) -> dict[str, str]:
        """收集用户实际传入（非 None）的字段为 {snake_case 列名: 值}，供 service 定点更新。"""
        return {
            key: value
            for key, value in self.model_dump().items()
            if value is not None
        }

