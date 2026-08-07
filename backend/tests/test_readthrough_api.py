"""Story 6.1：通读视图聚合 API 端到端测试（真实 HTTP + DB）。

覆盖（AC1/AC2/AC4/AC5/AC6/AC7，陷阱⑧/⑪）：
- 鉴权：无 token → 401 token_invalid；token 无效 → 401。
- AC1/AC2/AC7：返回全部已定稿章节（按 chapter_number 升序），后端已按
  READTHROUGH_PER_PAGE=6 段/页切好 pages/totalPages（前端不再二次分页）。
- AC5：draft 章节不进通读视图（不出现在 chapters）；hasUnfinalized=True。
- AC6 空态：无任何已定稿章节 → 200 chapters=[]、totalChapters=0——不报裸错、
  不 404（陷阱⑪：hasUnfinalized 仅信息提示，不阻断）。
- AC4 多租户：跨用户/不存在 project 同码 404（NFR3，不泄露作品存在性）。
- 多阶段：跨阶段累加章号正确取 stage_plan.chapters[序号-1].title；
  章标题缺省 / 无 stage_plan → 兜底「第 N 章」（防御 rendering 一致性）。
- 分页正确性：text 双换行分段后 len(pages)=ceil(N / 6)；单换行无空行也分段
  （防御 LLM 产物无空行的极端场景）。
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.main import app
from muse.models.account import User
from muse.models.chapter import Chapter
from muse.models.stage_plan import StagePlan
from muse.services.chapter_service import READTHROUGH_PER_PAGE, _split_pages
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    with _client:
        yield


def _create_project(headers: dict[str, str], title: str = "通读测试作品") -> str:
    resp = _client.post(
        "/api/projects",
        json={"mode": "guided", "title": title},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _seed_chapters(
    engine: Engine,
    *,
    user_id: uuid.UUID,
    project_id: str,
    chapters: list[tuple[int, str, str]],
) -> None:
    """落章节种子数据。`chapters` = [(chapter_number, status, text), ...]"""
    with Session(engine) as session:
        for chapter_number, status, text in chapters:
            session.add(
                Chapter(
                    user_id=user_id,
                    project_id=uuid.UUID(project_id),
                    chapter_number=chapter_number,
                    text=text,
                    status=status,
                )
            )
        session.commit()


def _seed_stage_plans(
    engine: Engine,
    *,
    user_id: uuid.UUID,
    project_id: str,
    plans: list[tuple[int, str, list[dict]]],
) -> None:
    """落阶段规划种子数据。`plans` = [(stage_number, goal, chapters_json), ...]"""
    with Session(engine) as session:
        for stage_number, goal, chapters in plans:
            session.add(
                StagePlan(
                    user_id=user_id,
                    project_id=uuid.UUID(project_id),
                    stage_number=stage_number,
                    goal=goal,
                    chapters=chapters,
                )
            )
        session.commit()


def _readthrough_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/readthrough"


# ---------- 鉴权（离线，不需 DB/Redis） ----------


def test_readthrough_without_token_returns_401() -> None:
    response = _client.get(_readthrough_url(str(uuid.uuid4())))
    assert response.status_code == 401
    assert response.json()["code"] == "token_invalid"


# ---------- _split_pages 单测（纯函数，离线） ----------


class TestSplitPages:
    """_split_pages 边界：空章 / 双换行分段 / 单换行无空行防御（防御 LLM 产物格式不稳）。"""

    def test_empty_text_returns_empty_pages(self) -> None:
        assert _split_pages("") == []
        assert _split_pages("   ") == []

    def test_single_paragraph_single_page(self) -> None:
        pages = _split_pages("雨下了一整夜。")
        assert pages == [["雨下了一整夜。"]]

    def test_paragraphs_spill_into_multiple_pages(self) -> None:
        paragraphs = [f"段 {i} 的内容。" for i in range(1, 14)]  # 13 段
        text = "\n\n".join(paragraphs)
        pages = _split_pages(text)
        # 13 段按 6 段/页 → 3 页（6 + 6 + 1）。
        assert len(pages) == 3
        assert pages[0] == paragraphs[0:6]
        assert pages[1] == paragraphs[6:12]
        assert pages[2] == paragraphs[12:13]

    def test_single_newline_falls_back_to_line_split(self) -> None:
        # LLM 产物若无空行只回车分段（极端场景）：不能把整章塌成 1 段。
        text = "第一句。\n第二句。\n第三句。"
        pages = _split_pages(text, per_page=2)
        assert pages == [["第一句。", "第二句。"], ["第三句。"]]

    def test_default_per_page_matches_readthrough_per_page(self) -> None:
        # 与前端 app.js:4579 常数对齐保护（改后端需同步前端）。
        assert READTHROUGH_PER_PAGE == 6


# ---------- 完整聚合响应（@requires_db） ----------


@requires_db
def test_readthrough_returns_finalized_chapters_with_pages(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """AC1/AC2/AC5/AC7：已定稿章节按章号升序直发；draft 不进 chapters，hasUnfinalized=True。"""
    user = make_user("readthrough-basic@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    paragraphs = [f"第 1 章段 {i}。" for i in range(1, 14)]  # 13 段 → 3 页
    _seed_chapters(
        db_engine,
        user_id=user.id,
        project_id=project_id,
        chapters=[
            (1, "finalized", "\n\n".join(paragraphs)),
            (2, "draft", "第 2 章尚未定稿，不能进通读。"),
            (3, "finalized", "第 3 章段 1。\n\n第 3 章段 2。"),
        ],
    )
    _seed_stage_plans(
        db_engine,
        user_id=user.id,
        project_id=project_id,
        plans=[
            (
                1,
                "首阶段",
                [
                    {"title": "打破日常", "brief": "第 1 章骨架"},
                    {"title": "不存在的证明", "brief": "第 2 章骨架"},
                    {"title": "代价显现", "brief": "第 3 章骨架"},
                ],
            )
        ],
    )

    response = _client.get(_readthrough_url(project_id), headers=headers)
    assert response.status_code == 200
    body = response.json()

    # 契约顶层字段（camelCase 边界）。
    assert set(body) == {"project", "chapters", "totalChapters", "hasUnfinalized"}
    assert body["project"] == {"title": "通读测试作品"}
    assert body["totalChapters"] == 2  # 只算已定稿
    assert body["hasUnfinalized"] is True  # 第 2 章 draft

    # 章节数组按 chapter_number 升序，仅含 finalized 两章。
    chapters = body["chapters"]
    assert [c["chapterNumber"] for c in chapters] == [1, 3]

    first = chapters[0]
    assert first["title"] == "打破日常"
    # 13 段按 6 段/页 → totalPages=3。
    assert first["totalPages"] == 3
    assert first["pages"][0] == paragraphs[0:6]
    assert first["pages"][1] == paragraphs[6:12]
    assert first["pages"][2] == paragraphs[12:13]

    third = chapters[1]
    assert third["title"] == "代价显现"
    assert third["totalPages"] == 1
    assert third["pages"] == [["第 3 章段 1。", "第 3 章段 2。"]]


@requires_db
def test_readthrough_empty_when_no_finalized(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """AC6：作品存在但无定稿章节 → 200 chapters=[]，不 404（陷阱⑪）。"""
    user = make_user("readthrough-empty@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    # 只有 draft 章 → hasUnfinalized=True 且 chapters=[]
    _seed_chapters(
        db_engine,
        user_id=user.id,
        project_id=project_id,
        chapters=[(1, "draft", "首章草稿")],
    )

    response = _client.get(_readthrough_url(project_id), headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["totalChapters"] == 0
    assert body["chapters"] == []
    assert body["hasUnfinalized"] is True


@requires_db
def test_readthrough_empty_when_no_chapters_at_all(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """AC6：完全无章节 → 200 chapters=[] 且 hasUnfinalized=False。"""
    user = make_user("readthrough-no-chapters@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    response = _client.get(_readthrough_url(project_id), headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["totalChapters"] == 0
    assert body["chapters"] == []
    assert body["hasUnfinalized"] is False


@requires_db
def test_readthrough_has_unfinalized_false_when_all_finalized(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("readthrough-all-done@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    _seed_chapters(
        db_engine,
        user_id=user.id,
        project_id=project_id,
        chapters=[
            (1, "finalized", "章1段1。"),
            (2, "finalized", "章2段1。"),
        ],
    )

    response = _client.get(_readthrough_url(project_id), headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["totalChapters"] == 2
    assert body["hasUnfinalized"] is False


@requires_db
def test_readthrough_chapter_title_from_stage_plan_across_stages(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """章标题按 stage_plan.chapters 累计法正确取；缺 title / 超范围 → 兜底「第 N 章」。"""
    user = make_user("readthrough-title@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    # 跨 2 个阶段共 4 章；第 4 章无 stage_plan.chapters 条目（超出范围）。
    _seed_chapters(
        db_engine,
        user_id=user.id,
        project_id=project_id,
        chapters=[
            (1, "finalized", "章1"),
            (2, "finalized", "章2"),
            (3, "finalized", "章3"),
            (4, "finalized", "章4"),
        ],
    )
    _seed_stage_plans(
        db_engine,
        user_id=user.id,
        project_id=project_id,
        plans=[
            (
                1,
                "首阶段",
                [
                    {"title": "第一章开局", "brief": "..."},
                    {"title": "第二章对立", "brief": "..."},
                ],
            ),
            (
                2,
                "中阶段",
                [
                    {"title": "第三章低谷", "brief": "..."},
                    # 第 4 章无骨架（阶段 2 只规划了 1 章）→ 兜底
                ],
            ),
        ],
    )

    response = _client.get(_readthrough_url(project_id), headers=headers)
    assert response.status_code == 200
    titles = [c["title"] for c in response.json()["chapters"]]
    assert titles == ["第一章开局", "第二章对立", "第三章低谷", "第 4 章"]


@requires_db
def test_readthrough_chapter_title_fallback_when_no_stage_plan(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """无任何 stage_plan（早期旧作品）→ 全部兜底「第 N 章」不报错。"""
    user = make_user("readthrough-no-plan@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    _seed_chapters(
        db_engine,
        user_id=user.id,
        project_id=project_id,
        chapters=[(1, "finalized", "章1"), (2, "finalized", "章2")],
    )

    response = _client.get(_readthrough_url(project_id), headers=headers)
    assert response.status_code == 200
    titles = [c["title"] for c in response.json()["chapters"]]
    assert titles == ["第 1 章", "第 2 章"]


@requires_db
def test_readthrough_foreign_project_returns_404(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """AC4/NFR3：跨用户访问 → 404；越权/不存在同码，不泄露作品存在性。"""
    owner = make_user("readthrough-owner@example.com")
    attacker = make_user("readthrough-attacker@example.com")
    project_id = _create_project(auth_headers(owner))

    _seed_chapters(
        db_engine,
        user_id=owner.id,
        project_id=project_id,
        chapters=[(1, "finalized", "owner 章 1")],
    )

    foreign = _client.get(_readthrough_url(project_id), headers=auth_headers(attacker))
    missing = _client.get(_readthrough_url(str(uuid.uuid4())), headers=auth_headers(attacker))

    for resp in (foreign, missing):
        assert resp.status_code == 404
        assert resp.json()["code"] == "project_not_found"


@requires_db
def test_readthrough_attacker_cannot_see_owner_draft_either(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """AC4/NFR3：即使本作品有章（draft+finalized 混合），跨用户也只能 404——
    hasUnfinalized 字段也严格租户隔离。"""
    owner = make_user("readthrough-mixed-owner@example.com")
    attacker = make_user("readthrough-mixed-attacker@example.com")
    project_id = _create_project(auth_headers(owner))

    _seed_chapters(
        db_engine,
        user_id=owner.id,
        project_id=project_id,
        chapters=[
            (1, "finalized", "定稿"),
            (2, "draft", "未定稿草稿"),
        ],
    )

    # 本人能看 → 200 + hasUnfinalized=True、chapters 只含 1 条
    own = _client.get(_readthrough_url(project_id), headers=auth_headers(owner))
    assert own.status_code == 200
    assert own.json()["hasUnfinalized"] is True
    assert len(own.json()["chapters"]) == 1

    # 跨用户严格 404——连 hasUnfinalized 都不允许拿到（NFR3 不泄露存在性）
    foreign = _client.get(_readthrough_url(project_id), headers=auth_headers(attacker))
    assert foreign.status_code == 404


@requires_db
def test_readthrough_invalid_project_id_returns_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """非 UUID 路由参数 → FastAPI 422（自动），不被 service 接住。"""
    user = make_user("readthrough-422@example.com")
    response = _client.get(
        "/api/projects/not-a-uuid/readthrough",
        headers=auth_headers(user),
    )
    assert response.status_code == 422
