"""Replay undelivered database jobs when Redis returns."""

import logging
import time
from uuid import uuid4

from redis import Redis
from rq import Queue

from app.config import settings
from app.store import Store

logger = logging.getLogger("taskhub.dispatcher")


def dispatch_once(store, queue):
    count = 0
    for job_id in store.pending():
        queue.enqueue(
            "app.worker.process_job",
            job_id,
            job_id=f"{job_id}-{uuid4()}",
            job_timeout=180,
            result_ttl=0,
            failure_ttl=86400,
        )
        store.mark_dispatched(job_id)
        count += 1
    return count


def main():
    logging.basicConfig(level=logging.INFO)
    config = settings()
    store = Store(config.database_url)
    queue = Queue("ai-tasks", connection=Redis.from_url(config.redis_url), serializer="json")
    while True:
        try:
            dispatch_once(store, queue)
        except Exception as exc:
            logger.warning("dispatch_failed error_type=%s", type(exc).__name__)
        time.sleep(2)


if __name__ == "__main__":
    main()
