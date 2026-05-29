# Econmesh API

Enterprise backend for the Econmesh platform — circular economy, ESG
traceability, blockchain anchoring, AI-ready.

Built as a **modular monolith** in Python 3.14 / FastAPI, designed so any
single module can graduate to its own microservice without re-architecting.

---

## Stack

| Concern          | Choice                                                  |
| ---------------- | ------------------------------------------------------- |
| Language         | Python **3.14** (free-threaded build supported)         |
| Web framework    | FastAPI (async)                                         |
| Validation       | Pydantic v2 / pydantic-settings                         |
| Database         | MongoDB via **PyMongo Async API** (`AsyncMongoClient`)  |
| Cache / sessions | Redis (`redis.asyncio`)                                 |
| Auth             | Firebase Admin SDK (ID token verification)              |
| Logging          | structlog (JSON in prod, console in dev)                |
| HTTP client      | httpx + tenacity                                        |
| Lint / format    | Ruff                                                    |
| Type checking    | Pyright (strict)                                        |
| Tests            | pytest + pytest-asyncio                                 |
| Packaging        | Poetry 2.x (PEP 621 `pyproject.toml`)                   |
| Container        | Multi-stage Docker, non-root, gunicorn + uvicorn        |
| Orchestration    | Docker Compose; ready for Kubernetes                    |

> Motor is intentionally **not** used — it reached end-of-life on
> 14-May-2026. The native PyMongo Async API is its official successor.

---

## Architecture

```
                ┌──────────────────────────────────────────┐
                │            Middleware stack              │
                │  RequestID → AccessLog → SecurityHeaders │
                │      → CORS → TrustedHost → Timeout      │
                └────────────────────┬─────────────────────┘
                                     │
                          /api/v1/<module>/...
                                     │
                  ┌──────────────────┴──────────────────┐
                  │              Router                 │
                  └──────────────────┬──────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │            Controller               │   ← HTTP only
                  └──────────────────┬──────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │             Service                 │   ← business rules
                  └──────────────────┬──────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │            Repository               │   ← data access
                  └────────┬──────────────────┬─────────┘
                           │                  │
                       MongoDB             Redis / Providers
                                       (Storage, Queue, AI, Blockchain)
```

Every module under `src/modules/<name>/` ships the same six files:

```
routes.py        FastAPI router
controller.py    Thin HTTP entry-points
service.py       Business rules
repository.py    Async Mongo access
schema.py        DTOs (request/response Pydantic models)
model.py         DomainDocument (persisted shape)
```

---

## Project layout

```
econmesh-api/
├── pyproject.toml             Poetry + ruff + pyright + pytest config
├── Dockerfile                 multi-stage production image
├── docker-compose.yml         api + mongo + redis
├── .env.example               document every env var
├── Makefile                   ergonomic shortcuts
└── src/
    ├── main.py                FastAPI factory + lifespan
    ├── core/                  config, db, firebase, security, logging, exceptions
    ├── shared/                middleware, dependencies, schemas, utils, constants
    ├── infrastructure/        redis client, storage/queue/ai/blockchain provider ABCs
    ├── modules/
    │   ├── auth/              ← fully functional reference module
    │   ├── users/             ← skeleton, ready to fill in
    │   ├── companies/         ← skeleton
    │   ├── circularity/       ← skeleton (ESG / material flows)
    │   ├── files/             ← skeleton (uploads)
    │   └── blockchain/        ← skeleton (on-chain anchoring)
    ├── workers/               background processes (see workers/README.md)
    ├── scripts/               create_indexes.py, seed_dev.py
    └── tests/                 pytest suite (health + auth smoke)
```

---

## Quick start

### 1. Prerequisites

- Python **3.14**
- Poetry **2.x**
- (For Docker path) Docker Desktop / Engine 24+ and Compose v2
- A Firebase project + service-account JSON

### 2. Local (no Docker)

```bash
cp .env.example .env             # then fill in real values
poetry install --with dev
poetry run uvicorn src.main:app --reload
```

Open <http://localhost:8000/docs> for the interactive OpenAPI UI.

### 3. With Docker Compose (recommended)

```bash
cp .env.example .env
mkdir -p secrets && cp /path/to/serviceAccountKey.json secrets/firebase.json
docker compose up --build
```

Endpoints:

- API → <http://localhost:8000>
- Swagger UI → <http://localhost:8000/docs>
- Liveness → `GET /health` → `{"status":"ok"}`
- Readiness → `GET /health/ready` (checks Mongo + Redis)

### 4. Common tasks

```bash
make dev          # uvicorn --reload
make test         # pytest with coverage
make lint         # ruff check src
make format       # ruff format src
make typecheck    # pyright
make check        # lint + typecheck + test
make indexes      # idempotent MongoDB index creation
make docker-up    # docker compose up -d
make docker-logs  # tail API logs
```

---

## Adding a new domain module

The `auth` module is the canonical reference. To add e.g. `inventory`:

1. **Copy the skeleton** layout of `src/modules/users/` into
   `src/modules/inventory/` and rename the classes.
2. **Define your document** in `model.py` as a subclass of `DomainDocument`,
   set `collection_name`, declare typed fields.
3. **Write the schemas** in `schema.py` — separate read DTOs (`*Response`)
   from write DTOs (`*Create` / `*Update`).
4. **Implement the repository** in `repository.py` — only Mongo concerns,
   no business rules.
5. **Implement the service** in `service.py` — orchestration, validation,
   side effects (Redis, providers, events).
6. **Expose endpoints** in `routes.py` and **register the router** in
   `src/main.py` (`_register_routers`).
7. **Add indexes** in `repository.ensure_indexes()` and wire that call
   into `src/scripts/create_indexes.py`.
8. **Add tests** in `src/tests/modules/inventory/`.

That's it. The middleware, exception handling, logging, RBAC and DI all
keep working without any change.

---

## Authentication flow

1. Client signs in with Firebase (web / mobile SDK) and obtains an ID token.
2. Client calls `POST /api/v1/auth/login` with `{ "id_token": "<jwt>" }`.
3. API verifies the token via Firebase Admin SDK, **upserts** the user into
   `users`, caches a small session in Redis, and returns the user + token
   introspection.
4. For subsequent calls, client sends `Authorization: Bearer <id_token>`.
5. The `get_current_user` dependency re-verifies each request (Firebase JWKS
   keys are cached by the SDK, so this is fast) and produces a typed
   `CurrentUser` injected into routes/services.
6. RBAC is enforced declaratively via `require_role(Role.ADMIN)` /
   `require_scopes("scope.write")` dependencies.

---

## Security baseline

- All inputs validated with Pydantic v2 (strict typing, length caps).
- OWASP-aligned security headers via `SecurityHeadersMiddleware`.
- CORS + Trusted Host driven by env config.
- Per-request timeout middleware (504 on exceeded).
- Secrets never logged (structlog scrubber redacts `password`, `token`, …).
- Bcrypt for any local password storage (Firebase handles end-user auth).
- Bearer token only — no cookies, no CSRF surface inside the API itself.
- Rate limiting prepared via `slowapi` (add `@limiter.limit(...)` to routes).
- Non-root Docker user (`uid 1000`).
- UUIDs (v7 when available) for all public identifiers; Mongo `ObjectId`
  never leaks to clients.

---

## Future extensions (intentional extension points)

- **Workers**: see `src/workers/README.md`. Reuse models/services; deploy
  separately (RabbitMQ/Kafka consumers, OCR pipelines, blockchain anchorers).
- **Storage / Queue / AI / Blockchain providers**: implement the ABCs in
  `src/infrastructure/` and inject the concrete instance via DI.
- **Observability**: structlog already emits JSON with `request_id` /
  `trace_id`; plug OpenTelemetry by adding an exporter in `setup_logging`.
- **Microservices**: every module is import-isolated (no cross-module imports
  except via shared schemas/utilities). Lifting a module out becomes a
  copy-paste + repointing of the DB connection.
- **Kubernetes**: `/health` (liveness) and `/health/ready` (readiness) are
  already provided; the Docker image is non-root and tini-init.

---

## License

Proprietary — Econmesh.
