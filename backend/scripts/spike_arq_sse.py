"""P2 ARQ + SSE 端到端骨架 spike（退风险验证脚本，非正式实现）。

目的：用真实 Redis 打出三个硬结论，喂给 Epic 2 Story 2.x 的编排/回传设计——
  1. ARQ + Redis broker 连通：任务能入队、worker 能消费；
  2. worker 真跑起：消费一个「模拟多步长时生成」任务（分 step 执行）；
  3. SSE 三事件真实推送一次：progress（多次）→ result，端到端经 Redis Pub/Sub 推到客户端。

架构对齐（architecture.md）：
  - 任务队列 ARQ（async 原生 + Redis broker）:197；
  - 交互 POST 提交→taskId→GET /events SSE:174,301,435；
  - 三事件名固定 progress/result/error:335，progress payload 至少 {step,percent} camelCase:336；
  - 进度经 Redis + SSE 推送:472，禁轮询:358 → 故用 Redis Pub/Sub（推模型）。

设计取舍：本 spike 单文件、同进程端到端（worker + FastAPI 同一 event loop 起），
一条命令可复跑、无需协调多进程；刻意不碰 core/sse.py / tasks/worker.py 正式占位
（正式实现待 Story 2.x，届时 payload 形态还要结合 P1 发现的 reasoning_content 处理）。
脚本自读 backend/.env 取 redis_url。

运行：cd backend && uv run python scripts/spike_arq_sse.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path

import httpx
import uvicorn
from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker
from fastapi import FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _BACKEND_ROOT / ".env"

# 模拟「写一章 = 多步」的长时任务：spike 用 3 步，每步一个 progress 事件。
_TOTAL_STEPS = 3
# Redis Pub/Sub 频道命名：按 taskId 隔离，SSE 端点订阅对应 taskId 的频道。
_CHANNEL = "task:{task_id}:events"


class SpikeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH), env_file_encoding="utf-8", extra="ignore"
    )
    redis_url: str = "redis://localhost:6379/0"


settings = SpikeSettings()


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def _publish(redis: Redis, task_id: str, event: str, data: dict) -> None:
    """把一个 SSE 事件 publish 到该 task 的 Redis 频道。事件名+payload 一起编码。"""
    channel = _CHANNEL.format(task_id=task_id)
    await redis.publish(channel, json.dumps({"event": event, "data": data}))


# ---------------------------------------------------------------------------
# ARQ worker 侧：模拟多步长时生成任务
# ---------------------------------------------------------------------------
async def generate_demo(ctx: dict, task_id: str, fail: bool = False) -> dict:
    """模拟「章节生成」多步任务：每步推一个 progress，末尾推 result。

    fail=True 时在第 2 步故意抛异常，用于验证 error 事件经同一链路推达（长时任务最关键路径）。
    ctx["redis"] 是 ARQ 注入的连接，但 Pub/Sub 用独立 Redis 连接更清晰（发布不复用 broker 连接）。
    """
    pub = Redis.from_url(settings.redis_url)
    try:
        for step in range(1, _TOTAL_STEPS + 1):
            await asyncio.sleep(0.3)  # 模拟一次 LLM 调用耗时
            if fail and step == 2:
                raise RuntimeError("模拟第 2 步 LLM 调用失败")
            await _publish(
                pub,
                task_id,
                "progress",
                {"step": step, "percent": round(step / _TOTAL_STEPS * 100)},
            )
        result = {"taskId": task_id, "chapterText": "（模拟生成的章节正文）", "steps": _TOTAL_STEPS}
        await _publish(pub, task_id, "result", result)
        return result
    except Exception as exc:  # noqa: BLE001  spike：worker 内异常也要推 error 事件
        # error 复用错误 envelope（architecture.md:336）：{code, message}。
        await _publish(pub, task_id, "error", {"code": "generate_failed", "message": str(exc)})
        raise
    finally:
        await pub.aclose()


class WorkerSettings:
    """ARQ WorkerSettings：spike 用，正式实现在 tasks/worker.py。"""

    functions = [generate_demo]
    redis_settings = _redis_settings()


# ---------------------------------------------------------------------------
# FastAPI 侧：POST 提交任务 + GET SSE 订阅
# ---------------------------------------------------------------------------
def build_app() -> FastAPI:
    app = FastAPI(title="spike-arq-sse")

    @app.post("/api/tasks/generate")
    async def submit(fail: bool = False) -> dict:
        """提交长时任务：入队 ARQ，返回 taskId（= job_id）。fail 透传 worker 验 error 路径。"""
        pool = await create_pool(_redis_settings())
        # 先生成一个稳定 task_id 作为 pubsub 频道键，并作为参数传给 worker。
        import uuid

        task_id = uuid.uuid4().hex
        await pool.enqueue_job("generate_demo", task_id, fail, _job_id=task_id)
        await pool.aclose()
        return {"taskId": task_id}

    @app.get("/api/tasks/{task_id}/events")
    async def events(task_id: str) -> EventSourceResponse:
        """SSE：订阅该 task 的 Redis 频道，把 progress/result/error 转发给客户端。"""
        channel = _CHANNEL.format(task_id=task_id)

        async def event_stream():
            sub = Redis.from_url(settings.redis_url)
            pubsub = sub.pubsub()
            await pubsub.subscribe(channel)
            try:
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                    payload = json.loads(msg["data"])
                    yield {"event": payload["event"], "data": json.dumps(payload["data"])}
                    # 收到终结事件即结束流。
                    if payload["event"] in ("result", "error"):
                        break
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
                await sub.aclose()

        return EventSourceResponse(event_stream())

    return app


# ---------------------------------------------------------------------------
# 编排：同进程起 worker + uvicorn，用 httpx 跑一次端到端，断言三事件
# ---------------------------------------------------------------------------
async def _submit_and_collect(client: httpx.AsyncClient, fail: bool) -> list[tuple[str, dict]]:
    """POST 提交（可选 fail）→ 连 SSE 流 → 收集事件直到 result/error。"""
    resp = await client.post("/api/tasks/generate", params={"fail": str(fail).lower()})
    resp.raise_for_status()
    task_id = resp.json()["taskId"]
    print(f"  ✓ POST 提交成功（fail={fail}），taskId={task_id}")

    events_seen: list[tuple[str, dict]] = []
    async with client.stream("GET", f"/api/tasks/{task_id}/events") as stream:
        cur_event = None
        async for line in stream.aiter_lines():
            if line.startswith("event:"):
                cur_event = line[len("event:"):].strip()
            elif line.startswith("data:") and cur_event:
                data = json.loads(line[len("data:"):].strip())
                events_seen.append((cur_event, data))
                print(f"  ← SSE 事件: {cur_event} {data}")
                if cur_event in ("result", "error"):
                    break
                cur_event = None
    return events_seen


async def run_client() -> int:
    """两轮端到端：① happy path（progress×N + result）；② error path（progress + error）。"""
    ok = True
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8123", timeout=30) as client:
        # ---- 第 1 轮：happy path ----
        print("\n[轮次 1] happy path：期望 progress×3 → result")
        events = await _submit_and_collect(client, fail=False)
        progress = [e for e in events if e[0] == "progress"]
        results = [e for e in events if e[0] == "result"]
        errors = [e for e in events if e[0] == "error"]
        if len(progress) == _TOTAL_STEPS:
            print(f"  ✓ progress 事件 {len(progress)} 个（期望 {_TOTAL_STEPS}）")
        else:
            print(f"  ✗ progress 事件 {len(progress)} 个（期望 {_TOTAL_STEPS}）")
            ok = False
        if len(results) == 1:
            print("  ✓ result 事件 1 个")
        else:
            print(f"  ✗ result 事件 {len(results)} 个（期望 1）")
            ok = False
        if errors:
            print(f"  ✗ happy path 意外收到 error：{errors}")
            ok = False
        if progress and all("step" in d and "percent" in d for _, d in progress):
            print("  ✓ progress payload 均含 {step, percent}")
        else:
            print("  ✗ progress payload 缺 step/percent")
            ok = False

        # ---- 第 2 轮：error path ----
        print("\n[轮次 2] error path：worker 第 2 步故意抛异常，期望 progress×1 → error")
        events = await _submit_and_collect(client, fail=True)
        progress = [e for e in events if e[0] == "progress"]
        errors = [e for e in events if e[0] == "error"]
        results = [e for e in events if e[0] == "result"]
        if len(errors) == 1:
            print("  ✓ error 事件 1 个")
        else:
            print(f"  ✗ error 事件 {len(errors)} 个（期望 1）")
            ok = False
        # error 复用错误 envelope（architecture.md:336）：至少含 code/message。
        if errors and all("code" in d and "message" in d for _, d in errors):
            print("  ✓ error payload 含 {code, message}（复用错误 envelope）")
        else:
            print("  ✗ error payload 缺 code/message")
            ok = False
        # 第 2 步就失败，故只应有第 1 步的 progress、且不应有 result。
        if len(progress) == 1:
            print("  ✓ 失败前仅 1 个 progress（第 2 步失败，符合预期）")
        else:
            print(f"  ⚠ 失败前 progress {len(progress)} 个（预期 1，非致命但值得注意）")
        if results:
            print(f"  ✗ error path 不应收到 result：{results}")
            ok = False
    return 0 if ok else 1


async def main() -> int:
    # 1. 起 uvicorn（后台 asyncio task）
    config = uvicorn.Config(build_app(), host="127.0.0.1", port=8123, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # 2. 起 ARQ worker（后台 asyncio task，同进程消费）
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        poll_delay=0.1,  # spike：加快轮询队列，减少等待
    )
    worker_task = asyncio.create_task(worker.async_run())

    # 3. 等 server 起来
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.1)

    print("=" * 60)
    print(f"P2 spike | redis={settings.redis_url}")
    print("=" * 60)
    print("\n[端到端] POST 提交 → worker 消费 → Redis Pub/Sub → SSE 回传")

    try:
        rc = await run_client()
    finally:
        # 4. 收尾：停 worker + server
        await worker.close()
        worker_task.cancel()
        server.should_exit = True
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        await server_task

    if rc == 0:
        print("\n✓ P2 spike 通过：ARQ broker 连通 + worker 消费 + SSE 三事件端到端推送成功。")
    else:
        print("\n✗ P2 spike 失败，见上方断言。")
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
