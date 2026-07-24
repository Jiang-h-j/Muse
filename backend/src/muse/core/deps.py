"""FastAPI 依赖聚合（core 横切基座）：受保护接口的鉴权入口。

`get_current_user` 是全项目受保护接口的统一鉴权依赖——从 Authorization: Bearer 提取 access token、
本地验签解出 user_id、查库取 User。1.4 起所有业务 router 依赖 `CurrentUser`（务必保持可复用）。
无/过期/非法 token 一律 401，并区分 token_expired / token_invalid 对接原型 expired 态（陷阱①）。
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import get_session
from muse.core.errors import ErrorEnvelope
from muse.core.security import TokenError, decode_access_token
from muse.models.account import User
from muse.repositories import account_repo

# auto_error=False：缺失/格式错的 Authorization 头不由 HTTPBearer 直接抛 403，
# 交我们统一转 401 token_invalid envelope，保证鉴权失败出口语义一致（都走原型 expired 态）。
_bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


def _token_error(reason: str) -> ErrorEnvelope:
    # token_expired / token_invalid 均附 detail.expired=true，前端据此跳 #/login?state=expired。
    return ErrorEnvelope(
        code=reason,
        message="会话已过期，请重新登录。",
        detail={"expired": True},
        http_status=401,
    )


async def get_current_user(session: SessionDep, credentials: _BearerDep) -> User:
    """解析 Bearer access token → 当前 User；失败抛 401 envelope（AC5）。"""
    if credentials is None:
        raise _token_error("token_invalid")

    try:
        user_id = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise _token_error(exc.reason) from exc

    user = await account_repo.get_user_by_id(session, user_id)
    if user is None:
        # token 签名有效但用户已不存在（如已注销）：视同失效，拒绝访问。
        raise _token_error("token_invalid")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
"""受保护接口鉴权依赖别名：路由参数标注为 CurrentUser 即自动完成 access token 校验 + 取用户。"""
