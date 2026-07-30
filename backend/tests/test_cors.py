"""Story 7.1 AC6 验证：dev CORS 中间件。

原型静态站（:4173）与后端（:8000）跨域，须放开前端 origin + Authorization 头，否则浏览器
预检/响应阶段拦截所有跨域请求，Epic 7 前端接线地基无从验证。不依赖 DB：预检（OPTIONS）与
简单请求的 CORS 头由中间件在到达路由前处理，TestClient 即可确定性覆盖。
"""

from fastapi.testclient import TestClient

from muse.core.settings import Settings
from muse.main import app

_ALLOWED_ORIGIN = "http://127.0.0.1:4173"
_DISALLOWED_ORIGIN = "http://evil.example.com"


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_settings_parses_comma_separated_origins() -> None:
    # 默认列原型两个本地 origin（127.0.0.1 与 localhost 是不同 origin，须都覆盖）。
    settings = Settings(cors_allow_origins="http://127.0.0.1:4173,http://localhost:4173")
    assert settings.cors_allow_origins_list == [
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]


def test_settings_origins_strip_and_drop_empty() -> None:
    # 尾随逗号 / 多余空格不产出空 origin。
    settings = Settings(cors_allow_origins=" http://a.com , , http://b.com ")
    assert settings.cors_allow_origins_list == ["http://a.com", "http://b.com"]


def test_preflight_allowed_origin_passes_with_authorization_header() -> None:
    # 浏览器带鉴权头的跨域请求会先发预检：须放行 Authorization 头与常用方法。
    resp = _client().options(
        "/api/auth/me",
        headers={
            "Origin": _ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN
    # 放行 Authorization 头（大小写不敏感，中间件回显请求头列表）。
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()


def test_actual_request_carries_allow_origin_header() -> None:
    # 简单/实际请求的响应须带 Access-Control-Allow-Origin，否则浏览器丢弃响应体。
    # /health 无需鉴权、无需 DB override 即可返回（DB 未就绪返 503 仍带 CORS 头）。
    resp = _client().get("/health", headers={"Origin": _ALLOWED_ORIGIN})
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN


def test_disallowed_origin_gets_no_allow_origin_header() -> None:
    # 未在白名单的 origin 不回显 Allow-Origin，浏览器据此拦截（不无脑 `*`）。
    resp = _client().get("/health", headers={"Origin": _DISALLOWED_ORIGIN})
    assert resp.headers.get("access-control-allow-origin") != _DISALLOWED_ORIGIN
