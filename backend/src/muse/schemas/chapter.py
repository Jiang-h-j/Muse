"""章节创作域 API schema（Story 4.3 / 4.4，AR4 camelCase 边界）。

- StagePlanChapter：单章骨架（title + brief）。
- StagePlanResponse：首个阶段规划（阶段目标 + 章节骨架列表），供进第一章时 GET 恢复 / SSE
  result 渲染侧栏。从 stage_plan ORM 行序列化（chapters JSONB 直接映射为章列表）。
- ChapterGenerateRequest（4.4）：POST 生成章节的请求体（可选本章想法）。
- ChapterTextResponse（4.4）：GET 章节正文恢复响应（终稿正文 + 版本 + 状态）。

触发端点复用 schemas.task.TaskSubmitResponse（返 taskId 供连 SSE），不在此重复定义。
"""

from muse.schemas.base import CamelModel


class StagePlanChapter(CamelModel):
    """阶段规划里的单章骨架：标题 + 一句话简介。

    title/brief 无下划线，边界 camelCase 与 snake_case 一致（无需别名转换）。对齐
    stage_plan.chapters JSONB 的元素结构 [{"title": ..., "brief": ...}]。
    """

    title: str
    brief: str


class StagePlanResponse(CamelModel):
    """首个阶段规划响应（AC2/AC3）：阶段目标 + 该阶段各章骨架。

    边界 camelCase（stage_number → stageNumber）。goal 为阶段总体目标文本；chapters 为章骨架
    列表（章数由 LLM 按剧情定、不写死）。GET 恢复端点与前端侧栏渲染的统一契约。
    """

    stage_number: int
    goal: str
    chapters: list[StagePlanChapter]


class ChapterGenerateRequest(CamelModel):
    """POST 生成章节的请求体（AC2/AC3）：本章想法可选填。

    边界 camelCase（chapter_idea → chapterIdea）。留空 = 「跳过并生成」，非空 = 「生成本章」
    （前端按钮文案切换，app.js:3080）。chapter_number 在路径、不在 body。
    """

    chapter_idea: str | None = None


class ChapterTextResponse(CamelModel):
    """GET 章节正文恢复响应（AC6）：终稿正文 + 版本 + 状态。

    边界 camelCase（chapter_number → chapterNumber、chapter_text → chapterText）。从 chapter
    ORM 行序列化。chapterText 字段名与 SSE result 的 `chapterText`（worker.py:245）一致——前端
    「GET 恢复」与「SSE result 渲染」走同一字段，渲染逻辑复用。revision/status 供 4.6/4.7 用。
    """

    chapter_number: int
    chapter_text: str
    revision: int
    status: str
