"""故事设定域 API schema：文风锚点抽取请求/响应（Story 3.2，AR4 camelCase 边界）。

响应/请求继承 CamelModel，边界自动 snake_case↔camelCase（如 sample_id↔sampleId、
style_profile↔styleProfile）。story 域 schema 起点——设定候选卡（3.3）、编辑/确认（3.4/3.5）
的 schema 后续在本文件按需扩。
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

