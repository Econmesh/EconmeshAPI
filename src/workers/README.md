# Workers

This folder hosts long-running background processes that are deployed
**separately** from the FastAPI process (different container, different
scale settings). They share the same code base so they can reuse models,
repositories and services, but they MUST NOT import `src.main`.

## Suggested layout when adding a worker

```
src/workers/
├── <worker_name>/
│   ├── __init__.py
│   ├── runner.py     # asyncio.run(main()) entrypoint
│   ├── handler.py    # message handler / job logic
│   └── README.md
```

## Stack guidelines

- **Queue consumers** (RabbitMQ, Kafka, Redis Streams) → use `arq`, `faststream`
  or hand-rolled `asyncio` loops on top of `aio-pika` / `aiokafka`.
- **Scheduled jobs** → `arq` cron or APScheduler; avoid running in the API
  process to keep horizontal scaling clean.
- **Reuse** the existing `MongoClientManager` / `RedisManager` singletons in
  the worker's own `asyncio.run` entry-point — the API's lifespan is **not**
  what manages them in the worker container.

## Operational notes

- One worker = one responsibility (anchoring, OCR, embeddings ingestion, etc.).
- Always emit structured logs (`structlog`) so events are correlated with the
  originating API request via `X-Request-ID` propagated through message headers.
- Use exponential back-off (`tenacity`) for any external call.
- Containers should declare `restart: on-failure` and a healthcheck that
  verifies the consumer is up-to-date with the broker.
