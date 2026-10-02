from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_lists_core_routes() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/v1/jobs", "/v1/jobs/{job_id}/approval", "/v1/jobs/{job_id}/transcript", "/v1/settings"} <= set(paths)
