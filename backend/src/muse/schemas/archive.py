"""归档页域 API schema（Story 5.3，AR4 camelCase 边界）。

归档页 `GET /api/projects/{project_id}/archive` 返回一份聚合 payload，包含：
- 设定圣经区（若已确认）：12 字段按 `PROFILE_CONTENT_FIELDS` 顺序、每个字段一条
  `ArchiveProfileItem`，`NN / 字段名` 编号（供前端 `padStart(2,'0')` 渲染）。
- 阶段分组：每个阶段一行 `ArchiveStageGroup`，含该阶段的章节卡片列表 + 未完成的章数。

所有 `user_id` 不出 schema（后置 `CurrentUser` 注入，类似 `ChapterTextResponse`），
`project_id` 从路由参数取、不出 response body。时间字段 ISO 8601 UTC（AR5）。
"""

from pydantic import Field

from muse.schemas.base import CamelModel


class ArchiveProfileItem(CamelModel):
    """单条设定字段：字段名（snake_case）、展示名（中文 label）、值（Text 全文）。

    边界 camelCase：field_name → fieldName、label 无下划线、value 无下划线。
    前端用 `String(index).padStart(2, "0")` 编号（`app.js:3950`：`index + 1` → `"01"`）。
    """

    field_name: str
    label: str
    value: str

# 12 字段 → 前端展示名（中文 label），供 `ArchiveProfileItem.label` 映射。
# 字段遍历顺序以 `story_bible_repo.PROFILE_CONTENT_FIELDS` 为单一事实源；本表只负责展示名。
PROFILE_LABELS: dict[str, str] = {
    "genre": "题材",
    "core_appeal": "核心吸引力",
    "protagonist": "主角",
    "main_conflict": "主要冲突",
    "world_rules": "关键世界规则",
    "overall_tone": "整体气质",
    "opening_hook": "开篇钩子",
    "power_system": "力量体系",
    "golden_finger": "金手指",
    "romance_line": "感情线",
    "faction_landscape": "势力格局",
    "style_profile": "文风锚点",
}


class ChapterCardSummary(CamelModel):
    """单章归档卡：章节编号、规划标题/简介与 data-agent 投影五要素。

    边界 camelCase：chapter_number → chapterNumber，五要素各列名与 `chapter_card`
    表字段一一对应。title/brief 来自所属 `stage_plan.chapters` 骨架，供归档列表卡片
    展示；五要素供详情弹窗展示。
    """

    chapter_number: int
    title: str
    brief: str
    what_happened: str
    character_changes: str
    new_facts_clues: str
    unresolved_hooks: str
    end_state: str


class ArchiveStageGroup(CamelModel):
    """一个阶段分组的归档摘要：阶段编号、阶段标题、已完成章数、章节卡片列表 + 未完成章数。

    边界 camelCase：stage_number → stageNumber、completed_count → completedCount、
    chapter_cards → chapterCards、missing → missing。title 为「第 N 阶段」（与原型阶段行标题
    一致）；missing = `len(stage_plan.chapters) - completed_count`。
    """

    stage_number: int
    title: str
    completed_count: int
    chapter_cards: list[ChapterCardSummary]
    missing: int = Field(
        default=0,
        description="仍需补写的章数（stage_plan.chapter_count - completed_count）",
    )


class ArchiveSummaryResponse(CamelModel):
    """归档页聚合 payload（AC1/AC2/AC3）：设定圣经区 + 阶段列表。

    边界 camelCase：profile_confirmed → profileConfirmed、profile_fields → profileFields、
    stages 无下划线。creator_id/creator_name 不在此（不属于归档页数据）。
    """

    profile_confirmed: bool = Field(
        default=False,
        description="设定是否已确认（confirmed=False 时 profile_fields=None）",
    )
    profile_fields: list[ArchiveProfileItem] | None = Field(
        default=None,
        description="已确认的 12 字段列表（confirmed=False 时为 None）",
    )
    stages: list[ArchiveStageGroup] = Field(
        default_factory=list,
        description="阶段分组列表（空列表 = 尚无任何阶段规划）",
    )