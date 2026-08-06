"""Story 5.1 验证：chapter_card 表落地（五要素、多租户、约束）。

本 story 无 API 层（只建表 + 模型 + 迁移），故用同步 ORM Session 直接造
user + project + chapter_card 断言 schema 契约，不走 HTTP 栈（同 test_story_bible.py
范式）：
- 插入一行五要素全填值：成功，落库可读。
- 不填任何五要素列：五列全取 server_default=""（空串，非 NULL）。
- 同 (user_id, project_id, chapter_number) 二次插入：撞
  uq_chapter_card_user_project_chapter 唯一约束抛 IntegrityError（一章一卡）。

DB 用例沿用 conftest 约定：需起容器并设 MUSE_DB_READY=1，否则 skip。
chapter_card 的 user_id/project_id FK 指向 user/project，conftest 的
TRUNCATE ... CASCADE 会连带清空，用例间天然隔离，无需另加清表。
"""

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from muse.models.account import User
from muse.models.chapter_card import ChapterCard
from muse.models.project import Project
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"cc-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="章节卡测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
def test_insert_five_elements_full(db_engine: Engine) -> None:
    """插入五要素全填值：成功，落库可读；chapter_number=3（非首章亦可）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            ChapterCard(
                user_id=user_id,
                project_id=project_id,
                chapter_number=3,
                what_happened="程野进入地下档案库，发现本不存在的走廊。",
                character_changes="程野决定用行动对抗周围人的否认。",
                new_facts_clues="未来日期的邮戳、第七码头邮局、来自未来的另一个程野。",
                unresolved_hooks="是谁寄出了信？程岚为何仍能留下痕迹？",
                end_state="程野打开标有未来日期的档案抽屉，再次听见程岚的声音。",
            )
        )
        session.commit()

    with Session(db_engine) as session:
        card = session.scalar(
            select(ChapterCard).where(ChapterCard.project_id == project_id)
        )
        assert card is not None
        assert card.chapter_number == 3
        assert card.what_happened.startswith("程野进入地下档案库")
        assert card.character_changes.startswith("程野决定用行动")
        assert "未来日期的邮戳" in card.new_facts_clues
        assert "谁寄出了信" in card.unresolved_hooks
        assert card.end_state.startswith("程野打开标有未来日期")


@requires_db
def test_five_elements_default_empty_string(db_engine: Engine) -> None:
    """完全不填任何五要素列：五列全取 server_default=""（必备但可空串语义，非 NULL）。

    对齐 story_bible 主干列先例——data-agent 某要素产空也能落库而不违反约束，
    由 service 上游空产守卫负责挡空产。
    """
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            ChapterCard(
                user_id=user_id, project_id=project_id, chapter_number=1
            )
        )
        session.commit()

    with Session(db_engine) as session:
        card = session.scalar(
            select(ChapterCard).where(ChapterCard.project_id == project_id)
        )
        assert card is not None
        for col in (
            card.what_happened,
            card.character_changes,
            card.new_facts_clues,
            card.unresolved_hooks,
            card.end_state,
        ):
            assert col == ""  # 空串，非 None


@requires_db
def test_unique_card_per_chapter(db_engine: Engine) -> None:
    """同 (user_id, project_id, chapter_number) 二次插入撞唯一约束 → IntegrityError。

    （一作品一章一张卡，5.2 单事务 chapter-commit 重跑 / ARQ 重试 max_tries=1
    不产生副本——与 chapter 表复合唯一键同键位。）
    """
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            ChapterCard(
                user_id=user_id,
                project_id=project_id,
                chapter_number=1,
                what_happened="第一章内容",
            )
        )
        session.commit()

    with Session(db_engine) as session:
        session.add(
            ChapterCard(
                user_id=user_id,
                project_id=project_id,
                chapter_number=1,
                what_happened="想覆盖第一章的第二张卡",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@requires_db
def test_different_chapters_independent(db_engine: Engine) -> None:
    """不同 chapter_number 各自占行——同作品多章卡片并存（5.3 归档页消费场景）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        for n, content in ((1, "第一章"), (2, "第二章"), (3, "第三章")):
            session.add(
                ChapterCard(
                    user_id=user_id,
                    project_id=project_id,
                    chapter_number=n,
                    what_happened=content,
                )
            )
        session.commit()

    with Session(db_engine) as session:
        cards = session.scalars(
            select(ChapterCard).where(ChapterCard.project_id == project_id)
        ).all()
        assert len(cards) == 3
        chapter_numbers = sorted(c.chapter_number for c in cards)
        assert chapter_numbers == [1, 2, 3]
