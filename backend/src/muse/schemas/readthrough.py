"""通读视图域 API schema（Story 6.1，AR4 camelCase 边界）。

通读视图把已定稿章节按 `READTHROUGH_PER_PAGE` 切好的「章 → 多页 → 每页多段」结构
一次性下发，前端只渲染 `pages[pageIndex]`、不做二次分页。`totalPages` 由后端
`len(pages)` 派生，**陷阱⑧**（前端不重复分页）。

- ReadthroughProject：作品标题（通读头部展示）。
- ReadthroughChapter：单章（chapterNumber + title + pages + totalPages），
  `pages[i]` 是第 i 页的段列表（每段一个字符串，不含 `<p>` 标签）。
- ReadthroughData / ReadthroughResponse：`ReadthroughResponse` 是 `ReadthroughData`
  的别名——service 内部用 `ReadthroughData` 表述（业务对象），router 边界用
  `ReadthroughResponse` 表述（响应契约）；两者结构相同。`totalChapters` = 已定稿章数；
  `hasUnfinalized` = 是否有未定稿章（仅供参考，不阻塞通读，**陷阱⑪**）。
"""

from muse.schemas.base import CamelModel


class ReadthroughProject(CamelModel):
    """通读页头部展示的作品信息。"""

    title: str


class ReadthroughChapter(CamelModel):
    """一章的通读 payload（AC2/AC3/AC7）。

    边界 camelCase：chapter_number → chapterNumber、total_pages → totalPages，title/pages
    无下划线。`pages[i]` 是第 i 页的段数组——后端按 `READTHROUGH_PER_PAGE` 切好直发；
    `totalPages` 由 `len(pages)` 派生（chapter 正文为空时 = 0，前端兜底空态分支）。
    """

    chapter_number: int
    title: str
    pages: list[list[str]]
    total_pages: int


class ReadthroughData(CamelModel):
    """通读视图聚合 payload（AC1/AC7，陷阱⑪）。

    边界 camelCase：total_chapters → totalChapters、has_unfinalized → hasUnfinalized。
    `chapters` 仅含已定稿章（按 chapter_number 升序）；`totalChapters` = `len(chapters)`；
    `hasUnfinalized` 仅供参考——通读视图为空时（无已定稿）前端走空态、不 404；
    有已定稿+未定稿共存时渲染已定稿、不因 hasUnfinalized=true 报错。
    """

    project: ReadthroughProject
    chapters: list[ReadthroughChapter]
    total_chapters: int
    has_unfinalized: bool


ReadthroughResponse = ReadthroughData
"""响应边界别名：ReadthroughResponse（API 契约）= ReadthroughData（业务组装结果）。

router 用 `ReadthroughResponse` 标注 response_model；service 内部组装用 `ReadthroughData`
名字（语义化）——两者指向同一个 Pydantic 类，避免无谓重复定义。
"""
