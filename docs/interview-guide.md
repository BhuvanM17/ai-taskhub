# Explain this project in an interview

Read the code and run the demo before using these talking points. Describe it as a portfolio project, not employer production work.

## 60-second overview

AI TaskHub is a Python backend for asynchronous text processing. A client authenticates with an API key, submits a job, and receives a job ID immediately. The request is saved in a relational database. A dispatcher sends pending jobs to Redis, and RQ workers process them and save validated results. I can run deterministic demo processing without a paid key or configure an LLM endpoint. The interesting backend parts are ownership boundaries, idempotent submissions, atomic job claiming, retries, and queue outage handling.

## Questions to prepare

1. **Why not call the model in the endpoint?** Long model calls consume web resources and make client timeouts harder to manage. A job API separates acceptance from completion.
2. **What if the client submits twice?** A database unique constraint scoped to the key owner deduplicates matching idempotency keys. Payload mismatches return 409.
3. **What if Redis is down?** The request is still durable in the database. The dispatcher can send it once Redis returns.
4. **Is execution exactly once?** No. Delivery can repeat, and atomic claiming suppresses duplicates in normal operation. Process crashes need recovery and may cause ambiguous external side effects.
5. **How do users avoid reading each other's results?** Each key maps to an owner ID, and every public list/detail query includes that owner filter.
6. **What do retries cover?** Timeouts, transport errors, HTTP 429 and 5xx, up to three calls with exponential backoff and jitter. Invalid JSON and permanent 4xx errors fail immediately.
7. **What would you improve next?** Migrations, quotas, key revocation, stale job leases, queue reconciliation, a data retention policy, and PostgreSQL integration/load tests.
8. **What did you test?** Real API requests and SQL operations, concurrent submissions and claims, RQ execution with fakeredis, and provider behavior through HTTP mock transports. These do not replace live infrastructure tests.

## A practical demonstration

Start Compose, generate a key, submit a job in Swagger, poll for completion, and replay the same request with the same idempotency key. Show the unchanged job ID. Generate a second key and show that it cannot read the first key's job. Then explain the queue delivery tests and the limitations you would address before production.
