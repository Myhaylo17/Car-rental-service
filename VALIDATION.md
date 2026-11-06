# Validation — local architecture

Executed in this environment with Python 3.12:

- pytest: **32 passed, 1 skipped**.
- Redis package uninstalled before the final test run; no Redis import required.
- Ruff lint passed; formatting check passed for 42 Python files.
- API startup/shutdown, health check and in-memory limiter tested without external services.
- Limiter tests cover expiry, concurrent requests, capacity, key reclamation and independent scopes.
- Console email backend tested without an SMTP connection.
- Existing API, authentication, bookings, favorites, assistant and outbox tests passed.
- One upstream Starlette/AnyIO deprecation warning emitted by TestClient.

Not executed here:

- Native Windows PowerShell scripts and full native MySQL startup.
- Real MySQL row-lock concurrency test: requires an isolated local MySQL test DB;
  instructions are in README.md. SQLite cannot verify MySQL lock semantics.
- Live Gemini call and actual SMTP delivery: require your credentials.

No Dockerfile, Compose configuration, Redis dependency or Redis configuration
is included in this version. The Linux Docker lockfile was removed; direct
cross-platform package pins remain in requirements.txt.
