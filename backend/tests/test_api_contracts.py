from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_includes_request_id_header():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_validation_errors_are_structured():
    response = client.get("/emails", params={"user_id": "not-a-uuid"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "validation_error"
    assert "request_id" in payload


def test_missing_route_uses_structured_error():
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"] == "http_error"
    assert "request_id" in payload


def test_send_email_endpoint_is_not_exposed():
    response = client.post("/emails/send")
    assert response.status_code in (404, 405)


def test_cors_preflight_allows_local_frontend():
    response = client.options(
        "/auth/google/start",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
