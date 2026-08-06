"""Story 5.1 验证：story_state 表落地（主角状态/世界规则/当前阶段快照、多租户）。

本 story 无 API 层（只建表 + 模型 + 迁移），故用同步 ORM Session 直接造
user + project + story_state 断言 schema 契约：
- 插入仅填 user_id+project_id 一行：三列快照取 server_default=""（空串非 NULL）。
- 同 (user_id, project_id) 二次插入：撞 uq_story_state_user_id_project_id
  唯一约束抛 IntegrityError（一作品一份当前快照，5.2 投影 UPSERT 同行 UPDATE）。

DB 用例沿用 conftest 约定：需起容器并设 MUSE_DB_READY=1。
"""

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from muse.models.account import User
from muse.models.project import Project
from muse.models.story_state import StoryState
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"ss-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="故事状态测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
def test_insert_minimal_defaults(db_engine: Engine) -> None:
    """插入仅填 user_id+project_id：三列快照取 server_default=""（必备但可空串语义）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(StoryState(user_id=user_id, project_id=project_id))
        session.commit()

    with Session(db_engine) as session:
        state = session.scalar(
            select(StoryState).where(StoryState.project_id == project_id)
        )
        assert state is not None
        assert state.protagonist_state == ""
        assert state.world_rules_state == ""
        assert state.current_stage == ""


@requires_db
def test_insert_full_snapshot(db_engine: Engine) -> None:
    """插入三列快照全填值：成功，落库可读（叙事快照可长于 story_bible 规则定义）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            StoryState(
                user_id=user_id,
                project_id=project_id,
                protagonist_state="程野心智动摇但行动果决，已开始独自追查。",
                world_rules_state=(
                    "灵气复苏、境界分九品；第 3 章新增补充——时间裂缝内法则失效，"
                    "邮戳预言效力可被抗拒。"
                ),
                current_stage="程野刚进入第七码头地下档案库，听见程岚的声音。",
            )
        )
        session.commit()

    with Session(db_engine) as session:
        state = session.scalar(
            select(StoryState).where(StoryState.project_id == project_id)
        )
        assert state is not None
        assert "程野心智动摇" in state.protagonist_state
        assert "时间裂缝内法则失效" in state.world_rules_state
        assert state.current_stage.startswith("程野刚进入第七码头")


@requires_db
def test_unique_state_per_project(db_engine: Engine) -> None:
    """同 (user_id, project_id) 二次插入撞唯一约束 → IntegrityError（一作品一份当前快照）。

    data-agent 投影 UPSERT 同行 UPDATE（5.2 单事务 chapter-commit 重跑 /
    ARQ 重试 max_tries=1 不产生副本——与 story_bible 复合唯一同先例）。
    """
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            StoryState(
                user_id=user_id,
                project_id=project_id,
                protagonist_state="第一版主角状态",
            )
        )
        session.commit()

    with Session(db_engine) as session:
        session.add(
            StoryState(
                user_id=user_id,
                project_id=project_id,
                protagonist_state="想开第二份快照",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
