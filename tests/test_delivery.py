from concurrent.futures import ThreadPoolExecutor

import fakeredis
import pytest
from rq import Queue, SimpleWorker

from app.config import settings
from app.dispatcher import dispatch_once
from app.store import Store


@pytest.fixture
def database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/delivery.db"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("AI_PROVIDER", "demo")
    settings.cache_clear()
    store = Store(url)
    store.initialize()
    owner = store.owner(store.create_key("delivery-test"))
    yield store, owner
    settings.cache_clear()


def test_real_rq_delivery_with_fake_redis(database):
    store, owner = database
    job = store.create_job(owner, "summarize", "Queued work. Done later.", None)
    redis = fakeredis.FakeRedis()
    queue = Queue("ai-tasks", connection=redis, serializer="json")
    assert dispatch_once(store, queue) == 1
    assert dispatch_once(store, queue) == 0
    SimpleWorker([queue], connection=redis, serializer="json").work(burst=True)
    assert store.get_job(job["id"], owner)["status"] == "succeeded"


def test_enqueue_failure_keeps_job_pending(database):
    store, owner = database
    job = store.create_job(owner, "extract", "hello", None)

    class OfflineQueue:
        def enqueue(self, *args, **kwargs):
            raise ConnectionError("Redis unavailable")

    with pytest.raises(ConnectionError):
        dispatch_once(store, OfflineQueue())
    assert job["id"] in store.pending()


def test_concurrent_duplicate_submissions(database):
    store, owner = database
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: store.create_job(owner, "summarize", "hello", "same-request"), range(12)
            )
        )
    assert len({job["id"] for job in results}) == 1


def test_only_one_worker_claims_job(database):
    store, owner = database
    job = store.create_job(owner, "summarize", "hello", None)
    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda _: store.claim(job["id"]), range(12)))
    assert sum(claim is not None for claim in claims) == 1
