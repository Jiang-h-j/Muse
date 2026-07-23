"""Story 1.1 验证：/health 端点契约、camelCase 边界（dbConnected）、error envelope。

不依赖真实 DB：check_db_connected 在连不上时返回 False 而非抛错，
故无 Docker 时端点仍返回 200（dbConnected=false），可离线验证契约与大小写边界。
DB 真实连通（dbConnected=true）在起容器后由本文件的 test_health_db_connected 覆盖。
"""

import os

import pytest
from fastapi.testclient import TestClient

from muse.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health_returns_200_and_camelcase_key() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    # AR4：边界字段为 camelCase，DB 侧 db_connected → API dbConnected
    assert "dbConnected" in body
    assert "db_connected" not in body
    assert body["status"] == "ok"
    assert isinstance(body["dbConnected"], bool)


def test_error_probe_returns_envelope() -> None:
    resp = client.get("/health/error-probe")
    # AR5：统一 error envelope {code, message, detail}
    assert resp.status_code == 400
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "probe_error"


def test_validation_error_uses_envelope() -> None:
    # 不存在的路由 → HTTPException 也走统一 envelope
    resp = client.get("/no-such-route")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}


@pytest.mark.skipif(
    os.getenv("MUSE_DB_READY") != "1",
    reason="需 docker-compose 起 PG 后设 MUSE_DB_READY=1 才验证真实连通",
)
def test_health_db_connected() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["dbConnected"] is True
