"""Story 5.3：归档页聚合 API 端到端测试（真实 HTTP + DB）。

覆盖：鉴权、camelCase 聚合响应、已确认设定、跨阶段真实 chapter_card 分组、
不存在/越权统一 404，以及未确认设定空态。
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.main import app
from muse.models.account import User
from muse.models.chapter_card import ChapterCard
from muse.models.stage_plan import StagePlan
from muse.models.story_bible import StoryBible
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    with _client:
        yield


def _create_project(headers: dict[str, str]) -> str:
    response = _client.post(
        "/api/projects",
        json={"mode": "guided", "title": "归档 API 测试作品"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _seed_archive(engine: Engine, *, user_id: uuid.UUID, project_id: str) -> None:
    project_uuid = uuid.UUID(project_id)
    with Session(engine) as session:
        session.add(
            StoryBible(
                user_id=user_id,
                project_id=project_uuid,
                status="confirmed",
                genre="都市悬疑",
                core_appeal="追查消失的人",
                protagonist="程野",
                main_conflict="城市不断改写过去",
                world_rules="记忆会在雨夜变化",
                overall_tone="潮湿压抑",
                opening_hook="未来来信",
            )
        )
        session.add_all(
            [
                StagePlan(
                    user_id=user_id,
                    project_id=project_uuid,
                    stage_number=1,
                    goal="第一阶段目标",
                    chapters=[
                        {"title": "未来来信", "brief": "程野收到一封未来来信。"},
                        {"title": "地下档案库", "brief": "程野寻找姐姐留下的痕迹。"},
                    ],
                ),
                StagePlan(
                    user_id=user_id,
                    project_id=project_uuid,
                    stage_number=2,
                    goal="第二阶段目标",
                    chapters=[
                        {"title": "决裂的地图", "brief": "城市的变化开始显露规律。"}
                    ],
                ),
            ]
        )
        session.add_all(
            [
                ChapterCard(
                    user_id=user_id,
                    project_id=project_uuid,
                    chapter_number=1,
                    stage_number=1,
                    what_happened="程野收到来自未来的信。",
                    character_changes="程野决定主动追查。",
                    new_facts_clues="未来邮戳。",
                    unresolved_hooks="是谁寄的信？",
                    end_state="程野进入地下档案库。",
                ),
                ChapterCard(
                    user_id=user_id,
                    project_id=project_uuid,
                    chapter_number=3,
                    stage_number=2,
                    what_happened="第二阶段正式开始。",
                    character_changes="程野不再单独行动。",
                    new_facts_clues="被改写的地图。",
                    unresolved_hooks="谁在控制城市？",
                    end_state="同伴选择了另一套记忆。",
                ),
            ]
        )
        session.commit()


def _archive_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/archive"


def test_archive_without_token_returns_401() -> None:
    response = _client.get(_archive_url(str(uuid.uuid4())))
    assert response.status_code == 401
    assert response.json()["code"] == "token_invalid"


@requires_db
def test_archive_returns_real_profile_and_stage_groups(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("archive-api@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _seed_archive(db_engine, user_id=user.id, project_id=project_id)

    response = _client.get(_archive_url(project_id), headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {"profileConfirmed", "profileFields", "stages"}
    assert body["profileConfirmed"] is True
    assert body["profileFields"][0] == {
        "fieldName": "genre",
        "label": "题材",
        "value": "都市悬疑",
    }
    assert len(body["stages"]) == 2

    first_stage = body["stages"][0]
    assert first_stage["stageNumber"] == 1
    assert first_stage["title"] == "第 1 阶段"
    assert first_stage["completedCount"] == 1
    assert first_stage["missing"] == 1
    assert first_stage["chapterCards"][0]["chapterNumber"] == 1
    assert first_stage["chapterCards"][0]["title"] == "第 1 章"
    assert first_stage["chapterCards"][0]["brief"] == "程野收到来自未来的信。"
    assert first_stage["chapterCards"][0]["whatHappened"] == "程野收到来自未来的信。"

    second_stage = body["stages"][1]
    assert second_stage["stageNumber"] == 2
    assert second_stage["chapterCards"][0]["chapterNumber"] == 3
    assert second_stage["chapterCards"][0]["title"] == "第 3 章"


@requires_db
def test_archive_unconfirmed_profile_returns_empty_profile(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("archive-empty-profile@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    response = _client.get(_archive_url(project_id), headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "profileConfirmed": False,
        "profileFields": None,
        "stages": [],
    }


@requires_db
def test_archive_foreign_and_missing_project_share_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    owner = make_user("archive-owner@example.com")
    attacker = make_user("archive-attacker@example.com")
    project_id = _create_project(auth_headers(owner))

    foreign = _client.get(_archive_url(project_id), headers=auth_headers(attacker))
    missing = _client.get(_archive_url(str(uuid.uuid4())), headers=auth_headers(attacker))

    for response in (foreign, missing):
        assert response.status_code == 404
        assert response.json()["code"] == "project_not_found"
