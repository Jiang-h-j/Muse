"""用量业务编排（Story 1.8，AR2：业务在 service，不在 router）。

- check_quota：**护栏校验框架**（AC2）——BYOK 优先短路放行、托管路径累计触顶抛 429，供 Epic 2
  生成链路在「发起生成前」调用。
- get_usage_view：**展示查询**（AC3）——只读、永不抛额度错误，供 GET /api/usage。
- record_usage：**记账写入编排**（AC1）——透传 repo + commit，供 Epic 2 Provider 层调用完 LLM
  后记账。**本 story 只提供此函数供 Epic 2 消费，不自行触发任何 LLM 调用、不接生成链路**
  （AR14 跨 epic 受控依赖，见 story Dev Notes「跨 Epic 边界」）。

护栏计量单位 = **tokens**（SUM(total_tokens) vs settings.free_quota_tokens，dev 定档）：一次 LLM
调用记一行、一章 5–10 次调用，按流水行数当章数会 5–10 倍虚高触顶，tokens 与记账粒度天然对齐。
额度重置口径 = **累计总量护栏**（V1 不做每日重置，省时区/重置时点复杂度）——原型「每天重置」文案
（app.js:2099）与本口径的差异留待前端接线切片对齐（本 story 不改 app.js）。

事务边界在本层（commit/rollback），业务错误抛 ErrorEnvelope 交全局 handler（延续 byok_service/
auth_service 范式）。依赖 byok_service 判 BYOK 豁免——单向 import（byok_service 不反向依赖本模块，
避免循环 import）。
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.models.account import UsageLedger
from muse.repositories import account_repo
from muse.services import byok_service


async def _is_byok_user(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """判当前账户是否已绑定 BYOK（AC4 豁免判据，陷阱③）。

    只需「是否绑定」的存在性布尔，故用 get_binding_status（byok_service.py:119，走
    get_byok_by_user 只查行是否存在、**不解密密钥**），而非 get_decrypted_key_for_user。
    后者会 AES-GCM 解密整串明文——既是每次 check_quota/GET /api/usage 的无谓开销、把明文
    密钥物化进内存，更会在密文篡改/主密钥轮转时抛 KeyDecryptError（security.py:197）：
    展示端点 GET /api/usage 只读、永不该因此 500（AC3/陷阱⑤）。存在性查询无此风险。
    """
    status = await byok_service.get_binding_status(session, user_id)
    return bool(status["bound"])


async def check_quota(session: AsyncSession, user_id: uuid.UUID) -> dict[str, object]:
    """护栏校验（AC2/AC4，供 Epic 2 生成前调用）：BYOK 优先短路，托管触顶抛 429。

    校验顺序**先判 BYOK 再判额度**（陷阱③）：已绑定 BYOK → 立即放行、根本不查 usage 累计
    （BYOK 不占免费额度，AC4）；顺序反了会让 BYOK 重度用户被托管额度误拦。
    托管路径未触顶 → 返回剩余额度信息、不抛错；触顶（已用 >= 阈值，陷阱④）→ 抛 quota_exceeded
    429（沿用登录限流 too_many_attempts 先例），detail 带前端可读位、不静默失败（AR6）。
    """
    if await _is_byok_user(session, user_id):
        return {"quota_applies": False, "billing_path": "byok"}

    used = await account_repo.sum_hosted_usage(session, user_id)
    quota = get_settings().free_quota_tokens
    # 触顶判定用 >=（已用满即拦，story 推荐）：used == quota 属触顶，不再放行。
    if used >= quota:
        raise ErrorEnvelope(
            code="quota_exceeded",
            message="免费额度已用完，绑定自己的 API Key 即可继续创作。",
            detail={"quotaExceeded": True, "used": used, "quota": quota},
            http_status=429,
        )
    return {
        "quota_applies": True,
        "billing_path": "hosted",
        "used": used,
        "quota": quota,
        "remaining": quota - used,
    }


async def get_usage_view(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[str, object]:
    """展示查询（AC3）：返回当前账户用量与剩余免费额度，供 GET /api/usage。

    **只读、永不抛额度错误**（陷阱⑤）——查看用量不该因触顶而失败，用户额度用完了更需看到
    「已用完」的满格态。与 check_quota 分离：本函数永远返回当前状态。
    BYOK 用户 → {billingPath:"byok", quotaApplies:false, used/quota/remaining 为 null}（前端展示
    「走自有 Key、不占免费额度」，对齐原型 byok tab 文案 app.js:2104）；托管用户 → 具体用量。
    reset_at 恒为 None（V1 累计总量护栏，不做每日重置）。
    """
    if await _is_byok_user(session, user_id):
        return {
            "billing_path": "byok",
            "quota_applies": False,
            "used": None,
            "quota": None,
            "remaining": None,
            "reset_at": None,
        }

    used = await account_repo.sum_hosted_usage(session, user_id)
    quota = get_settings().free_quota_tokens
    # remaining 用 max(0, ...) 兜底：即便未来触顶后仍有记账（防御性），展示不出现负数。
    return {
        "billing_path": "hosted",
        "quota_applies": True,
        "used": used,
        "quota": quota,
        "remaining": max(0, quota - used),
        "reset_at": None,
    }


async def record_usage(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    billing_path: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost: Decimal,
    project_id: uuid.UUID | None = None,
    model_name: str | None = None,
) -> UsageLedger:
    """记账写入编排（AC1，供 Epic 2 Provider 层调用完 LLM 后消费的接口）。

    透传 account_repo.record_usage + commit（repo 只 flush，事务边界在此）。billing_path 由调用方
    （Provider 层）依该账户 BYOK 绑定态传 hosted/byok（陷阱⑧）——本 story 只提供此函数、存该列，
    **不自行触发 LLM 调用、不判定 billing_path**（AR14 跨 epic 受控留茬，见 Dev Notes）。
    """
    usage = await account_repo.record_usage(
        session,
        user_id=user_id,
        project_id=project_id,
        billing_path=billing_path,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost=cost,
        model_name=model_name,
    )
    await session.commit()
    await session.refresh(usage)
    return usage
