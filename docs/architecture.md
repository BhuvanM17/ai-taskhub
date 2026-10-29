# Design decisions

## Separation of responsibilities

FastAPI accepts and validates input without calling a model. SQLAlchemy persists the job and its ownership boundary. A separate dispatcher publishes pending rows to Redis. RQ executes work outside the web process. The database remains the source of truth for status and results.

## Why RQ

FastAPI BackgroundTasks would simplify a demo, but does not provide an independent persistent queue. Celery offers richer routing and scheduling at the cost of a larger configuration surface. RQ fits this project's small set of Python-only task types. The Redis transport uses JSON serialization rather than pickle.

## Why database-backed dispatch

Writing a database row and enqueueing to Redis cannot be committed atomically. If the API tried to do both, an outage between those writes could lose work. Pending rows are replayed by the dispatcher. Duplicates are possible when enqueue succeeds before the delivery timestamp commits, so claiming is a conditional SQL update. Only one queued-to-running transition wins.

## Ownership and idempotency

API keys contain 256 bits of random token entropy and are stored as SHA-256 digests. A fast hash is suitable for high-entropy generated tokens; it is not a password hashing strategy. Key IDs own jobs. All public job reads filter by owner, including list queries. The database enforces uniqueness of `(owner_id, idempotency_key)`; a payload fingerprint distinguishes a replay from a conflicting request.

## Concurrency

Sync FastAPI handlers run blocking database calls in the framework thread pool. SQLAlchemy manages connection pooling; connections are scoped to operations rather than held during inference. Worker throughput scales with worker processes, bounded by provider limits and database capacity. This repository does not claim a tested capacity of 30 or any other number of simultaneous users.

## Provider boundary

Remote responses are untrusted data. Pydantic validates parsed JSON before results are persisted. Network timeouts and bounded retries prevent an indefinite wait in common error cases. The RQ hard timeout is a final process-level bound, with the known stale-running recovery limitation documented in the README. Prompt instructions reduce accidental instruction following; they are not a security boundary or a guarantee against prompt injection.

## Operational boundaries

Database readiness does not imply a healthy dispatcher or worker. Monitor queue age and worker activity separately. Logs omit text and credentials. For a production deployment, add schema migrations, key lifecycle management, quotas, per-client authorization policy, operator recovery, and retention controls.

## Official references

- [RQ queue documentation](https://python-rq.org/docs/)
- [RQ jobs and JSON serialization](https://python-rq.org/docs/jobs/)
- [FastAPI security tools](https://fastapi.tiangolo.com/reference/security/)
- [SQLAlchemy Core](https://docs.sqlalchemy.org/en/20/core/)
