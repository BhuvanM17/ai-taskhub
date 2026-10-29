"""Database owns job state; Redis is only a delivery mechanism."""

import hashlib
import json
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
keys = Table(
    "api_keys",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("digest", String(64), unique=True, nullable=False),
)
jobs = Table(
    "jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("owner_id", String(36), ForeignKey("api_keys.id"), nullable=False, index=True),
    Column("task", String(20), nullable=False),
    Column("text", Text, nullable=False),
    Column("status", String(20), nullable=False, index=True),
    Column("idempotency_key", String(128)),
    Column("fingerprint", String(64), nullable=False),
    Column("result", JSON),
    Column("error", String(200)),
    Column("attempts", Integer, default=0, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("dispatched_at", DateTime(timezone=True)),
    UniqueConstraint("owner_id", "idempotency_key"),
)


def now():
    return datetime.now(timezone.utc)


class Conflict(Exception):
    pass


class Store:
    def __init__(self, url):
        kwargs = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=kwargs, pool_pre_ping=True)

    def initialize(self):
        metadata.create_all(self.engine)

    def create_key(self, name):
        token = "ath_" + secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            conn.execute(
                insert(keys).values(
                    id=str(uuid4()), name=name, digest=hashlib.sha256(token.encode()).hexdigest()
                )
            )
        return token

    def owner(self, token):
        with self.engine.connect() as conn:
            return conn.execute(
                select(keys.c.id).where(keys.c.digest == hashlib.sha256(token.encode()).hexdigest())
            ).scalar_one_or_none()

    def create_job(self, owner_id, task, text, idempotency_key):
        fingerprint = hashlib.sha256(json.dumps([task, text]).encode()).hexdigest()
        values = dict(
            id=str(uuid4()),
            owner_id=owner_id,
            task=task,
            text=text,
            status="queued",
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            attempts=0,
            created_at=now(),
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(jobs).values(**values))
        except IntegrityError:
            if not idempotency_key:
                raise
            with self.engine.connect() as conn:
                existing = (
                    conn.execute(
                        select(jobs).where(
                            jobs.c.owner_id == owner_id, jobs.c.idempotency_key == idempotency_key
                        )
                    )
                    .mappings()
                    .one()
                )
            if existing["fingerprint"] != fingerprint:
                raise Conflict("Idempotency key already used for a different request") from None
            return dict(existing)
        return self.get_job(values["id"], owner_id)

    def get_job(self, job_id, owner_id):
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(jobs).where(jobs.c.id == job_id, jobs.c.owner_id == owner_id))
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def list_jobs(self, owner_id, limit, offset):
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(jobs)
                    .where(jobs.c.owner_id == owner_id)
                    .order_by(jobs.c.created_at.desc(), jobs.c.id)
                    .limit(limit)
                    .offset(offset)
                ).mappings()
            ]

    def claim(self, job_id):
        with self.engine.begin() as conn:
            result = conn.execute(
                update(jobs)
                .where(jobs.c.id == job_id, jobs.c.status == "queued")
                .values(status="running", attempts=jobs.c.attempts + 1)
            )
            if not result.rowcount:
                return None
            return dict(conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().one())

    def finish(self, job_id, result=None, error=None):
        with self.engine.begin() as conn:
            conn.execute(
                update(jobs)
                .where(jobs.c.id == job_id, jobs.c.status == "running")
                .values(
                    status="failed" if error else "succeeded",
                    result=result,
                    error=error,
                    finished_at=now(),
                )
            )

    def pending(self):
        with self.engine.connect() as conn:
            return list(
                conn.execute(
                    select(jobs.c.id)
                    .where(jobs.c.status == "queued", jobs.c.dispatched_at.is_(None))
                    .limit(100)
                ).scalars()
            )

    def mark_dispatched(self, job_id):
        with self.engine.begin() as conn:
            conn.execute(update(jobs).where(jobs.c.id == job_id).values(dispatched_at=now()))
