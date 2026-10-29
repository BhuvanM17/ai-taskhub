import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from app.worker import process_job


@pytest.fixture
def setup(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/test.db")
    store.initialize()
    key = store.create_key("Alice")
    other = store.create_key("Bob")
    with TestClient(create_app(store)) as client:
        yield client, store, {"X-API-Key": key}, {"X-API-Key": other}


def submit(client, headers, **kw):
    return client.post(
        "/v1/jobs",
        headers=headers,
        json={"task": "summarize", "text": "A useful backend. It runs jobs.", **kw},
    )


def test_requires_auth(setup):
    client, _, _, _ = setup
    assert client.get("/v1/jobs").status_code == 401
    assert client.get("/v1/jobs", headers={"X-API-Key": "bad"}).status_code == 401


def test_submit_process_and_read(setup):
    client, store, headers, _ = setup
    response = submit(client, headers)
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    process_job(job["id"], store=store)
    result = client.get(f"/v1/jobs/{job['id']}", headers=headers).json()
    assert result["status"] == "succeeded"
    assert result["result"]["provider"] == "demo"
    assert result["result"]["summary"]


def test_tenant_isolation(setup):
    client, _, headers, other = setup
    job = submit(client, headers).json()
    assert client.get(f"/v1/jobs/{job['id']}", headers=other).status_code == 404
    assert client.get("/v1/jobs", headers=other).json() == []


def test_idempotency_replays_and_conflicts(setup):
    client, _, headers, _ = setup
    headers = {**headers, "Idempotency-Key": "request-123"}
    first = submit(client, headers)
    second = submit(client, headers)
    assert first.json()["id"] == second.json()["id"]
    assert submit(client, headers, text="Different content").status_code == 409
    assert len(client.get("/v1/jobs", headers=headers).json()) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"task": "unknown", "text": "hello"},
        {"task": "summarize", "text": "   "},
        {"task": "summarize", "text": "x" * 20001},
    ],
)
def test_validation(setup, payload):
    client, _, headers, _ = setup
    assert client.post("/v1/jobs", headers=headers, json=payload).status_code == 422


def test_duplicate_delivery_does_not_repeat_inference(setup):
    client, store, headers, _ = setup
    job = submit(client, headers).json()
    calls = []

    def provider(task, text):
        calls.append(text)
        return {"summary": "done", "provider": "test"}

    process_job(job["id"], store=store, provider=provider)
    process_job(job["id"], store=store, provider=provider)
    assert len(calls) == 1


def test_failure_does_not_leak_provider_error(setup):
    client, store, headers, _ = setup
    job = submit(client, headers).json()

    def broken(task, text):
        raise RuntimeError("secret-api-key")

    process_job(job["id"], store=store, provider=broken)
    response = client.get(f"/v1/jobs/{job['id']}", headers=headers)
    assert response.json()["status"] == "failed"
    assert "secret-api-key" not in response.text


def test_extraction(setup):
    client, store, headers, _ = setup
    job = submit(client, headers, task="extract", text="Contact demo@example.com").json()
    process_job(job["id"], store=store)
    result = client.get(f"/v1/jobs/{job['id']}", headers=headers).json()["result"]
    assert result["emails"] == ["demo@example.com"]


def test_pagination_and_request_id(setup):
    client, _, headers, _ = setup
    submit(client, headers)
    response = client.get("/v1/jobs?limit=1", headers=headers)
    assert len(response.json()) == 1
    assert response.headers["X-Request-ID"]
    assert client.get("/v1/jobs?limit=101", headers=headers).status_code == 422


def test_health(setup):
    client, _, _, _ = setup
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200


def test_rejects_nul_for_postgres_compatibility(setup):
    client, _, headers, _ = setup
    assert submit(client, headers, text="hello\x00world").status_code == 422
