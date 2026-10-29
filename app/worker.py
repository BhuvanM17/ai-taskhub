import logging

from app.config import settings
from app.providers import run_task
from app.store import Store

logger = logging.getLogger("taskhub.worker")


def process_job(job_id, *, store=None, provider=None):
    database = store or Store(settings().database_url)
    job = database.claim(job_id)
    if job is None:
        return
    try:
        result = (provider or run_task)(job["task"], job["text"])
    except Exception as exc:
        logger.warning("job_id=%s failed error_type=%s", job_id, type(exc).__name__)
        database.finish(
            job_id, error="Processing failed. Check provider configuration or retry later."
        )
    else:
        database.finish(job_id, result=result)
