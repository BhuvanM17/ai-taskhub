import logging
import time
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.security import APIKeyHeader
from sqlalchemy import text

from app.config import settings
from app.schemas import JobCreate, JobView
from app.store import Conflict, Store

logger = logging.getLogger("taskhub.api")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_app(store=None):
    database = store or Store(settings().database_url)
    api = FastAPI(
        title="AI TaskHub",
        version="0.1.0",
        description="Durable, authenticated background text processing jobs.",
    )

    def owner(token: Annotated[str | None, Depends(api_key_header)]):
        owner_id = database.owner(token) if token else None
        if not owner_id:
            raise HTTPException(401, "Invalid or missing API key")
        return owner_id

    @api.middleware("http")
    async def trace(request, call_next):
        request_id = str(uuid4())
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s status=%s duration_ms=%.1f",
            request_id,
            request.method,
            response.status_code,
            (time.monotonic() - start) * 1000,
        )
        return response

    @api.get("/health/live", tags=["Health"])
    def live():
        return {"status": "ok"}

    @api.get("/health/ready", tags=["Health"])
    def ready():
        try:
            with database.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"database": "ok"}
        except Exception:
            raise HTTPException(503, "Database unavailable") from None

    @api.post("/v1/jobs", response_model=JobView, status_code=202, tags=["Jobs"])
    def submit(
        payload: JobCreate,
        owner_id: Annotated[str, Depends(owner)],
        idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
    ):
        try:
            return database.create_job(owner_id, payload.task, payload.text, idempotency_key)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None

    @api.get("/v1/jobs", response_model=list[JobView], tags=["Jobs"])
    def listing(
        owner_id: Annotated[str, Depends(owner)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return database.list_jobs(owner_id, limit, offset)

    @api.get("/v1/jobs/{job_id}", response_model=JobView, tags=["Jobs"])
    def detail(job_id: str, owner_id: Annotated[str, Depends(owner)]):
        job = database.get_job(job_id, owner_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return job

    return api


app = create_app()
