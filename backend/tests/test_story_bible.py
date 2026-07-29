"""Story 3.1 验证：story_bible 表落地（12 字段 schema、多租户、约束）。

本 story 无 API 层（只建表 + 模型 + 迁移），故用同步 ORM Session 直接造
user + project + story_bible 断言 schema 契约，不走 HTTP 栈：
- 插入一行：7 主干列填值、4 特化列 + style_profile 留 NULL → 成功，且主干列
  server_default="" 生效（不填即空串、非 NULL）。
- 特化列可存 NULL（AC3「不匹配的特化列存空、不报错」）。
- 同 (user_id, project_id) 二次插入 → 撞 uq_story_bible_user_id_project_id 唯一约束
  抛 IntegrityError（一作品一圣经，AC5）。

DB 用例沿用 conftest 约定：需起容器并设 MUSE_DB_READY=1，否则 skip。story_bible 的
user_id/project_id FK 指向 user/project，conftest 的 TRUNCATE ... CASCADE 会连带清空，
用例间天然隔离，无需另加清表。
"""

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from muse.models.account import User
from muse.models.project import Project
from muse.models.story_bible import StoryBible
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"sb-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()  # 拿 user.id 供 project FK
        project = Project(user_id=user.id, title="设定测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
def test_insert_trunk_only_leaves_specialized_null(db_engine: Engine) -> None:
    """插入仅填主干列的一行：成功，特化列 + style_profile 为 NULL，未填主干列为空串。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            StoryBible(
                user_id=user_id,
                project_id=project_id,
                genre="修仙",
                core_appeal="凡人流稳健升级的爽感",
                protagonist="林凡：想长生；缺陷是多疑",
                main_conflict="与宗门长老争夺机缘；反派镜像同求长生却不择手段",
                world_rules="灵气复苏、境界分九品",
                overall_tone="冷峻克制",
                opening_hook="开篇捡到一枚会说话的戒指",
                # 主干 7 列全填；特化 4 列 + style_profile 全部不给（留 NULL）
            )
        )
        session.commit()

    with Session(db_engine) as session:
        bible = session.scalar(
            select(StoryBible).where(StoryBible.project_id == project_id)
        )
        assert bible is not None
        # 主干填值落库
        assert bible.genre == "修仙"
        assert bible.protagonist.startswith("林凡")
        # 特化 4 列未填 → NULL
        assert bible.power_system is None
        assert bible.golden_finger is None
        assert bible.romance_line is None
        assert bible.faction_landscape is None
        # style_profile 未抽取 → NULL（Story 3.2 才写入）
        assert bible.style_profile is None


@requires_db
def test_trunk_columns_default_empty_string(db_engine: Engine) -> None:
    """完全不填任何主干列：7 主干列取 server_default="" 而非 NULL（必备但可空串语义）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(StoryBible(user_id=user_id, project_id=project_id))
        session.commit()

    with Session(db_engine) as session:
        bible = session.scalar(
            select(StoryBible).where(StoryBible.project_id == project_id)
        )
        assert bible is not None
        for col in (
            bible.genre,
            bible.core_appeal,
            bible.protagonist,
            bible.main_conflict,
            bible.world_rules,
            bible.overall_tone,
            bible.opening_hook,
        ):
            assert col == ""  # 空串，非 None


@requires_db
def test_specialized_columns_accept_values(db_engine: Engine) -> None:
    """特化列 + style_profile 可正常写入非空值（激活态）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(
            StoryBible(
                user_id=user_id,
                project_id=project_id,
                genre="系统爽文",
                power_system="等级制",
                golden_finger="签到系统",
                romance_line="双洁",
                faction_landscape="三大帝国鼎立",
                style_profile="第一人称、短句、快节奏",
            )
        )
        session.commit()

    with Session(db_engine) as session:
        bible = session.scalar(
            select(StoryBible).where(StoryBible.project_id == project_id)
        )
        assert bible is not None
        assert bible.golden_finger == "签到系统"
        assert bible.style_profile == "第一人称、短句、快节奏"


@requires_db
def test_unique_bible_per_project(db_engine: Engine) -> None:
    """同 (user_id, project_id) 二次插入撞唯一约束 → IntegrityError（一作品一圣经）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with Session(db_engine) as session:
        session.add(StoryBible(user_id=user_id, project_id=project_id, genre="言情"))
        session.commit()

    with Session(db_engine) as session:
        session.add(StoryBible(user_id=user_id, project_id=project_id, genre="悬疑"))
        with pytest.raises(IntegrityError):
            session.commit()
