"""Story 1.1 验证：/health 端点契约、camelCase 边界（dbConnected）、error envelope。

/health 的 DB 连通两态（200/503）用 dependency override 注入假 session 确定性覆盖，
不依赖运行环境是否真有 DB；真实连通另由 test_health_db_connected（需起容器）兜底。
"""

import os
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from muse.core.db import get_session
from muse.core.errors import register_exception_handlers
from muse.main import app
from muse.schemas.base import CamelModel, UTCDateTime


class _FakeSession:
    """假 session：execute 命中即视为 DB 通；raises=True 则模拟连接失败。"""

    def __init__(self, raises: bool) -> None:
        self._raises = raises

    async def execute(self, _stmt: object) -> object:
        if self._raises:
            raise RuntimeError("db down")

        class _R:
            def scalar_one(self) -> int:
                return 1

        return _R()


def _client_with_db(connected: bool) -> TestClient:
    async def _override():
        yield _FakeSession(raises=not connected)

    app.dependency_overrides[get_session] = _override
    return TestClient(app, raise_server_exceptions=False)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_health_db_up_returns_200_and_camelcase_key() -> None:
    resp = _client_with_db(connected=True).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    # AR4：边界字段为 camelCase，DB 侧 db_connected → API dbConnected
    assert "dbConnected" in body
    assert "db_connected" not in body
    assert body["dbConnected"] is True
    assert body["status"] == "ok"


def test_health_db_down_returns_503() -> None:
    # 探针按状态码判活：DB 不通须返回 503，避免已宕实例被判健康。
    resp = _client_with_db(connected=False).get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["dbConnected"] is False
    assert body["status"] == "degraded"


def test_error_probe_returns_envelope() -> None:
    resp = TestClient(app, raise_server_exceptions=False).get("/health/error-probe")
    # AR5：统一 error envelope {code, message, detail}
    assert resp.status_code == 400
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "probe_error"


def test_unknown_route_uses_http_error_envelope() -> None:
    # 不存在的路由 → 404 StarletteHTTPException 也走统一 envelope
    resp = TestClient(app, raise_server_exceptions=False).get("/no-such-route")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "http_error"


class _Payload(BaseModel):
    secret: str
    age: int


def _make_probe_client() -> TestClient:
    probe = FastAPI()
    register_exception_handlers(probe)

    @probe.post("/echo")
    async def echo(_: _Payload) -> dict[str, str]:
        return {}

    return TestClient(probe, raise_server_exceptions=False)


def test_validation_error_envelope_omits_input() -> None:
    # 真正触发 RequestValidationError(422)，验证 envelope 且脱敏（不回显提交的原始值）。
    resp = _make_probe_client().post("/echo", json={"secret": "hunter2"})  # 缺 age → 422
    assert resp.status_code == 422
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "validation_error"
    # 脱敏：提交的敏感原始值不得反射进响应
    assert "hunter2" not in resp.text


def test_utc_datetime_serializes_with_z_suffix() -> None:
    # AR5：UTCDateTime 边界序列化为带 Z 后缀的 ISO 8601 UTC，而非 Pydantic 默认 +00:00。
    class _M(CamelModel):
        created_at: UTCDateTime

    dumped = _M(created_at=datetime(2026, 7, 24, 8, 0, 0, tzinfo=UTC)).model_dump(
        mode="json", by_alias=True
    )
    assert dumped["createdAt"] == "2026-07-24T08:00:00Z"


@pytest.mark.skipif(
    os.getenv("MUSE_DB_READY") != "1",
    reason="需 docker-compose 起 PG 后设 MUSE_DB_READY=1 才验证真实连通",
)
def test_health_db_connected() -> None:
    # 真实 DB：用真实 get_session（不 override），验证端到端连通。
    resp = TestClient(app, raise_server_exceptions=False).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dbConnected"] is True
    assert body["status"] == "ok"
