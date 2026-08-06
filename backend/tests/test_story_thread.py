"""Story 5.1 验证：story_thread 表落地（伏笔/线索、多租户、状态语义）。

本 story 无 API 层（只建表 + 模型 + 迁移），故用同步 ORM Session 直接造
user + project + story_thread 断言 schema 契约，不走 HTTP 栈：
- 插入仅必填列：status 默认 "open"、resolved_chapter_number 默认 NULL、
  content 允许空串。
- 显式写入 resolved_chapter_number：可写非空值（回收态）。
- 同一 (user_id, project_id) 多行独立 thread 并存：无复合唯一约束
  （5.2 投影时由 service 用 last_touched_chapter_number + 内容匹配自行去重）。

DB 用例沿用 conftest 约定：需起容器并设 MUSE_DB_READY=1。
story_thread 的 user_id/project_id FK 指向 user/project，conftest 的
TRUNCATE ... CASCADE 会连带清空，用例间天然隔离。
"""

import uuid

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.models.account import User
from muse.models.project import Project
from muse.models.story_thread import StoryThread
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"st-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="伏笔测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
def test_insert_minimal_defaults(db_engine: Engine) -> None:
    """插入仅填必填列：status 默认 "open"、resolved_chapter_number 默认 NULL。

    - content 必填但可空串（同 story_clue.value 先例）。
    - last_touched_chapter_number 业务上应等于 introduced_chapter_number
      （新增 = 最初埋点），DB 层不强制，由 service 显式赋同值。
    """
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            StoryThread(
                user_id=user_id,
                project_id=project_id,
                content="未来日期的邮戳预示着寄信人来自未来",
                introduced_chapter_number=1,
                last_touched_chapter_number=1,
            )
        )
        session.commit()

    with Session(db_engine) as session:
        thread = session.scalar(
            select(StoryThread).where(StoryThread.project_id == project_id)
        )
        assert thread is not None
        assert thread.status == "open"  # server_default
        assert thread.resolved_chapter_number is None  # 未回收 = NULL
        assert thread.introduced_chapter_number == 1
        assert thread.last_touched_chapter_number == 1


@requires_db
def test_content_default_empty_string(db_engine: Engine) -> None:
    """content 不显式填：取 server_default=""（必备但可空串语义）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            StoryThread(
                user_id=user_id,
                project_id=project_id,
                introduced_chapter_number=2,
                last_touched_chapter_number=2,
            )
        )
        session.commit()

    with Session(db_engine) as session:
        thread = session.scalar(
            select(StoryThread).where(StoryThread.project_id == project_id)
        )
        assert thread is not None
        assert thread.content == ""  # 空串，非 None


@requires_db
def test_resolved_chapter_number_accepts_value(db_engine: Engine) -> None:
    """显式写入 resolved_chapter_number + status='resolved'：可写非空值（回收态）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        thread = StoryThread(
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            introduced_chapter_number=1,
            last_touched_chapter_number=5,
        )
        session.add(thread)
        session.flush()
        # 第 5 章回收：翻 status + 写 resolved_chapter_number
        thread.status = "resolved"
        thread.resolved_chapter_number = 5
        session.commit()

    with Session(db_engine) as session:
        thread = session.scalar(
            select(StoryThread).where(StoryThread.project_id == project_id)
        )
        assert thread is not None
        assert thread.status == "resolved"
        assert thread.resolved_chapter_number == 5
        assert thread.last_touched_chapter_number == 5


@requires_db
def test_multiple_open_threads_coexist(db_engine: Engine) -> None:
    """同一 (user_id, project_id) 多行独立 thread 并存：无复合唯一约束。

    5.2 投影时由 service 用 last_touched_chapter_number + 内容匹配自行去重，
    避免重跑产生重复 thread——这与 chapter_card（一章一卡天然幂等键）形成对照。
    """
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            StoryThread(
                user_id=user_id,
                project_id=project_id,
                content="邮戳伏笔",
                introduced_chapter_number=1,
                last_touched_chapter_number=1,
            )
        )
        session.add(
            StoryThread(
                user_id=user_id,
                project_id=project_id,
                content="会浮现文字的信纸",
                introduced_chapter_number=1,
                last_touched_chapter_number=2,
            )
        )
        session.add(
            StoryThread(
                user_id=user_id,
                project_id=project_id,
                content="第七码头地下档案库",
                introduced_chapter_number=3,
                last_touched_chapter_number=3,
            )
        )
        session.commit()

    with Session(db_engine) as session:
        threads = session.scalars(
            select(StoryThread).where(StoryThread.project_id == project_id)
        ).all()
        assert len(threads) == 3
        contents = {t.content for t in threads}
        assert contents == {"邮戳伏笔", "会浮现文字的信纸", "第七码头地下档案库"}
