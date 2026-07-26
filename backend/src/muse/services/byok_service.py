"""BYOK 业务编排（Story 1.7，AR2：业务在 service，不在 router）。

- bind_or_replace_key：校验 → AES-GCM 加密 → upsert → commit（AC1 绑定 / AC3 替换）。
- get_binding_status：查本人绑定 → 组掩码状态载荷（AC4）。
- unbind_key：删除本人 BYOK → commit（AC3 解绑，幂等）。
- get_decrypted_key_for_user：供 Epic 2 Provider 层消费的内部接口（AC5），返回明文或 None。

安全红线（陷阱①）：明文 API Key 绝不落库（只存密文）、绝不进日志、绝不出 API 边界
（响应只回掩码）。事务边界在此层（repo 只 flush/delete）；校验失败抛 ErrorEnvelope。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.errors import ErrorEnvelope
from muse.core.security import decrypt_api_key, encrypt_api_key
from muse.models.account import ByokKey
from muse.repositories import account_repo

# 受支持的 provider 枚举（与 schema Literal 一致，service 侧双保险；AC2）。
_ALLOWED_PROVIDERS = frozenset({"deepseek", "claude", "custom"})
# API Key 长度上限：防超大输入放大加密/DB 开销（参照 project title max_length 风格）。
_KEY_MAX_LENGTH = 512
# 掩码保留的明文尾部位数（仅尾 4 位不足以泄露密钥）。
_SUFFIX_LEN = 4


def _mask_suffix(normalized_key: str) -> str:
    """算掩码用的明文尾部：Key 长于 _SUFFIX_LEN 时取尾 _SUFFIX_LEN 位，否则全打码。

    切片 `key[-4:]` 对 ≤4 字符的 Key 会返回整串（如 "abc"[-4:] == "abc"），使 key_suffix
    列存下全量明文、maskedKey 回显整串——击穿「明文绝不落库/回显」安全红线（陷阱①）。故对
    长度 ≤ _SUFFIX_LEN 的 Key 一律返回等长掩码 `*`，绝不让尾 4 位逻辑退化成暴露整串。
    """
    if len(normalized_key) > _SUFFIX_LEN:
        return normalized_key[-_SUFFIX_LEN:]
    return "*" * len(normalized_key)


def _validate_key(plaintext: str) -> str:
    """校验并归一化 API Key：去首尾空白后非空、长度 ≤ 上限（AC2）。

    空/纯空白/超长抛 ErrorEnvelope（400）。返回 strip 后的 Key（供加密与算尾 4 位，
    避免复制粘贴带入的首尾空白污染密文）。**不校验 Key 是否真实有效**——发测试请求验活属
    Provider 层且引入外部调用与延迟，V1 只做格式校验。
    """
    normalized = plaintext.strip()
    if not normalized:
        raise ErrorEnvelope(
            code="byok_invalid_key",
            message="API Key 不能为空。",
            http_status=400,
        )
    if len(normalized) > _KEY_MAX_LENGTH:
        raise ErrorEnvelope(
            code="byok_invalid_key",
            message=f"API Key 长度超出上限（≤{_KEY_MAX_LENGTH}）。",
            http_status=400,
        )
    return normalized


def _validate_provider(provider: str) -> None:
    """校验 provider 为受支持枚举（AC2）；非法抛 ErrorEnvelope（400）。

    schema Literal 已在边界拦非法 provider（422），此处为 service 直调场景兜底。
    """
    if provider not in _ALLOWED_PROVIDERS:
        raise ErrorEnvelope(
            code="byok_invalid_provider",
            message="不支持的模型提供方。",
            http_status=400,
        )


def status_payload(byok: ByokKey | None) -> dict[str, object]:
    """把 BYOK 记录（或 None）转为绑定状态载荷（AC4），供 router 转 ByokStatusResponse。

    已绑定 → {bound:True, provider, masked_key}；未绑定 → {bound:False, provider:None,
    masked_key:None}。掩码用中性格式 `…`+尾 4 位（陷阱⑦：不硬编码 sk- 前缀，Claude/自定义
    provider 前缀不同）。**绝不含明文 Key**（AC1）。
    """
    if byok is None:
        return {"bound": False, "provider": None, "masked_key": None}
    return {
        "bound": True,
        "provider": byok.provider,
        "masked_key": f"…{byok.key_suffix}",
    }


async def bind_or_replace_key(
    session: AsyncSession, user_id: uuid.UUID, provider: str, plaintext_key: str
) -> ByokKey:
    """绑定/替换本人 BYOK（AC1/AC3）：校验 → 加密 → upsert → commit，返回 ByokKey。

    先校验（provider 枚举 + Key 格式），再加密（明文绝不落库），算尾 4 位供掩码，upsert 覆盖或
    插入（唯一约束保证每账户至多一条）。校验失败抛 ErrorEnvelope 交全局 handler。
    """
    _validate_provider(provider)
    normalized_key = _validate_key(plaintext_key)
    encrypted = encrypt_api_key(normalized_key)
    key_suffix = _mask_suffix(normalized_key)
    byok = await account_repo.upsert_byok(
        session,
        user_id=user_id,
        provider=provider,
        encrypted_key=encrypted,
        key_suffix=key_suffix,
    )
    await session.commit()
    # 替换分支的 updated_at 由 DB 侧 onupdate 计算，commit 后 ORM 内存态不会自动同步，
    # refresh 拉回真实时间戳（照 project_service.rename_project 范式，陷阱②同源）。
    await session.refresh(byok)
    return byok


async def get_binding_status(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[str, object]:
    """查询本人 BYOK 绑定状态（AC4）：已绑定回掩码、未绑定回空态。绝不回显明文。"""
    byok = await account_repo.get_byok_by_user(session, user_id)
    return status_payload(byok)


async def unbind_key(session: AsyncSession, user_id: uuid.UUID) -> None:
    """解绑本人 BYOK（AC3）：删除记录 → commit。删 0 行也幂等成功。

    幂等语义：解绑是「确保没有绑定」的意图，未绑定时再解绑不报错（DELETE → 204）。后续生成
    自然回落托管路径（本 story 不实现，见 Dev Notes 跨 Epic 边界）。
    """
    await account_repo.delete_byok(session, user_id)
    await session.commit()


async def get_decrypted_key_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> str | None:
    """取当前账户已解密的 API Key 明文（AC5，供 Epic 2 Provider 层消费的内部接口）。

    已绑定 → decrypt_api_key 返回明文；未绑定 → None。明文只在内存中传给（未来的）Provider，
    **绝不 log、不落库、不出 API 边界**。解密失败（篡改/主密钥变更）由 decrypt_api_key 抛
    KeyDecryptError 向上传播（陷阱⑥：不 silently 返回空串误当合法 Key）——消费方据此决定报错
    或回落。**本 story 只提供此函数，不接生成链路**（AR12/AR14，Epic 2 落地）。
    """
    byok = await account_repo.get_byok_by_user(session, user_id)
    if byok is None:
        return None
    return decrypt_api_key(byok.encrypted_key)
