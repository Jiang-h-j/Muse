"""P1 DeepSeek 联调 spike（退风险验证脚本，非正式实现）。

目的：用真实 API 打出三个硬结论，喂给 Epic 2 Story 2.1 的 LLMProvider 设计——
  1. 联通性：OpenAI SDK 切 base_url 指向 DeepSeek，双档模型各发一次 chat 能正常返回；
  2. count_tokens 精度：本地字符估算 vs API usage 实际 token 的偏差（决定护栏预检可信度）；
  3. 双档差异：deepseek-v4-pro（思考）/ deepseek-v4-flash（快）的延迟、token 用量、响应特征。

设计取舍：本 spike 刻意不碰 src 主代码、不建 Provider 抽象（providers/llm.py 是 Story 2.1
才建）。脚本自读 backend/.env（不打印 key 明文），纯外呼不碰 DB，验证完保留作参考。

运行：cd backend && uv run python scripts/spike_deepseek.py
      cd backend && uv run python scripts/spike_deepseek.py --models v4-pro  # 只跑单档
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 与 src 同源，定位到 backend/.env（脚本在 backend/scripts/ 下）。
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _BACKEND_ROOT / ".env"

# 架构文档（architecture.md:108,196）定的双档模型名，spike 要验证其是否与真实 API 一致。
_DEFAULT_MODELS = {
    "v4-pro": "deepseek-v4-pro",  # 思考档：起草/审查
    "v4-flash": "deepseek-v4-flash",  # 快档：提取/轻任务
}

# spike 用的中文短 prompt：能体现网文创作场景、便于观察双档响应差异。
_PROMPT = "用两句话描述一个修仙世界的开场，要有画面感。"

# 控制单次调用成本与延迟：spike 只验证联通与计量，不需要长输出。
_MAX_TOKENS = 200


class SpikeSettings(BaseSettings):
    """只读 backend/.env 里 DeepSeek 相关配置；extra=ignore 避免与主 Settings 字段冲突。"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = ""
    # 架构未写死 base_url，官方默认 https://api.deepseek.com；允许 .env 覆盖。
    deepseek_base_url: str = "https://api.deepseek.com"


def estimate_tokens_local(text: str) -> int:
    """本地粗估 token 数（无官方离线 tokenizer 时的近似）。

    经验系数：CJK 汉字 ≈ 0.6 token/字，其余（英文/数字/标点）≈ 0.3 token/字。
    这是护栏「生成前预检」若要本地预估时的候选算法，本 spike 量化它与 API 实际值的偏差。
    """
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    other = len(text) - cjk
    return round(cjk * 0.6 + other * 0.3)


@dataclass
class CallResult:
    label: str
    model: str
    ok: bool
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    content: str = ""
    reasoning: str = ""
    error: str = ""


def probe_models(client) -> list[str]:
    """探测账号可用模型列表——若架构文档里的模型名与真实 API 不符，这里能立刻暴露。"""
    try:
        resp = client.models.list()
        return [m.id for m in resp.data]
    except Exception as exc:  # noqa: BLE001  spike 探测，任何异常都如实报出
        print(f"  [models.list 探测失败] {type(exc).__name__}: {exc}")
        return []


def call_chat(client, label: str, model: str) -> CallResult:
    """对单个模型发一次 chat，记录延迟、usage、响应内容与（思考档的）reasoning。"""
    started = time.monotonic()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _PROMPT}],
            max_tokens=_MAX_TOKENS,
            stream=False,
        )
        latency = time.monotonic() - started
        msg = resp.choices[0].message
        usage = resp.usage
        return CallResult(
            label=label,
            model=model,
            ok=True,
            latency_s=latency,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            content=(msg.content or "").strip(),
            # 思考档可能返回 reasoning_content（类 o1），标准字段没有则为空。
            reasoning=(getattr(msg, "reasoning_content", "") or "").strip(),
        )
    except Exception as exc:  # noqa: BLE001  spike 要如实报出每种失败（模型名错/鉴权/网络）
        return CallResult(
            label=label,
            model=model,
            ok=False,
            latency_s=time.monotonic() - started,
            error=f"{type(exc).__name__}: {exc}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepSeek 联调 spike")
    parser.add_argument(
        "--models",
        nargs="*",
        choices=list(_DEFAULT_MODELS),
        default=list(_DEFAULT_MODELS),
        help="要测的档位（默认全跑）：v4-pro / v4-flash",
    )
    parser.add_argument("--prompt", default=_PROMPT, help="自定义测试 prompt")
    args = parser.parse_args()

    settings = SpikeSettings()
    if not settings.deepseek_api_key:
        print("✗ 未在 backend/.env 读到 DEEPSEEK_API_KEY，请先配置后再跑。")
        return 2

    # 延迟到此处再 import，openai 缺失时报错更清晰。
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )

    print("=" * 64)
    print(f"DeepSeek spike | base_url={settings.deepseek_base_url}")
    print(f"key 尾 4 位=…{settings.deepseek_api_key[-4:]} (仅示尾号，不打印全值)")
    print("=" * 64)

    print("\n[1] 探测可用模型列表 …")
    available = probe_models(client)
    if available:
        print(f"  账号可用模型（{len(available)}）：{', '.join(available)}")
    else:
        print("  （未取到模型列表，继续按架构文档模型名直接调用）")

    print(f"\n[2] 双档 chat 调用 | prompt={args.prompt!r}")
    results: list[CallResult] = []
    for label in args.models:
        model = _DEFAULT_MODELS[label]
        expect = "✓在列表" if model in available else "⚠不在列表(可能名字变了)"
        print(f"\n  → {label} ({model}) {expect if available else ''}")
        r = call_chat(client, label, model)
        results.append(r)
        if r.ok:
            print(f"    ✓ {r.latency_s:.2f}s | usage: prompt={r.prompt_tokens} "
                  f"completion={r.completion_tokens} total={r.total_tokens}")
            if r.reasoning:
                print(f"    [reasoning] {r.reasoning[:80]}…")
            print(f"    [content] {r.content[:120]}")
        else:
            print(f"    ✗ 失败：{r.error}")

    ok_results = [r for r in results if r.ok]
    if not ok_results:
        print("\n✗ 全部调用失败——先看上面的错误信息（多半是模型名或 base_url/鉴权）。")
        return 1

    # 结论 2：count_tokens 精度——本地估算 vs API 实际 prompt_tokens 偏差。
    print("\n" + "=" * 64)
    print("[3] count_tokens 精度：本地字符估算 vs API 实际 prompt_tokens")
    print("=" * 64)
    local_est = estimate_tokens_local(args.prompt)
    print(f"  prompt={args.prompt!r}")
    print(f"  本地估算(CJK×0.6+其余×0.3) = {local_est} tokens")
    for r in ok_results:
        diff = r.prompt_tokens - local_est
        pct = (diff / r.prompt_tokens * 100) if r.prompt_tokens else 0.0
        print(f"  {r.label:9s} API prompt_tokens={r.prompt_tokens:4d} | "
              f"估算偏差 {diff:+d} ({pct:+.1f}%)")
    print("  注：API prompt_tokens 含 role/格式开销，天然略高于纯文本估算；"
          "偏差稳定即可作预检基准。")

    # 结论 3：双档差异汇总。
    print("\n" + "=" * 64)
    print("[4] 双档差异汇总")
    print("=" * 64)
    print(f"  {'档位':9s} {'延迟s':>7s} {'prompt':>7s} {'compl':>7s} {'total':>7s}  reasoning")
    for r in ok_results:
        print(f"  {r.label:9s} {r.latency_s:7.2f} {r.prompt_tokens:7d} "
              f"{r.completion_tokens:7d} {r.total_tokens:7d}  {'有' if r.reasoning else '无'}")

    print("\n✓ spike 完成。以上数据用于 Story 2.1 LLMProvider 的模型名/计量/选档设计。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
