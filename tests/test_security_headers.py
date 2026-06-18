"""Security response headers are stamped on app routes and skip CSP on docs."""

from api.security import docs_urls


def test_docs_enabled_only_in_demo_mode():
    assert docs_urls(True)["openapi_url"] == "/openapi.json"
    assert docs_urls(False) == {"docs_url": None, "redoc_url": None, "openapi_url": None}


def test_hardening_headers_on_app_route(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_csp_skipped_on_docs_but_other_headers_kept(client):
    r = client.get("/openapi.json")
    assert "content-security-policy" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"
