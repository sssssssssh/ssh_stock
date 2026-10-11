# M16.2.1 Reliability & Evidence Integrity Closeout

## Scope

This closeout hardens the optional M16.2 chat runtime without changing the eight M16.1
read-only tools, authentication model, strategy configuration, research calculations or
frontend. Chat remains disabled by default.

Delivered controls:

- one monotonic end-to-end deadline across context, provider retries, tool/cache/audit,
  evidence compilation and terminal persistence;
- remaining-budget propagation into tool soft timeouts and PostgreSQL
  `statement_timeout`;
- structured FACT, INFERENCE and COMPARISON claims with deterministic record-level
  Evidence validation;
- backend comparison policy for same-date ranking, entity-over-time, independent
  backtests and TRAIN/OOS;
- normalized request-content hashing and strict request ID replay rules;
- forward-only, history-preserving migrations `0048_m16_2_1_request_hash` and
  `0049_m16_2_1_hash_name`.

## Request identity policy

The request hash is SHA-256 over canonical JSON containing the normalized user content,
chat ID, owner ID and contract version. Content normalization applies Unicode NFKC,
converts CRLF/CR to LF, trims whitespace surrounding the complete message and removes
trailing whitespace from each remaining line. Internal line order and leading indentation
inside the message remain significant.

A completed turn replays only when the stored hash matches. Reusing a request ID with
different content, or matching a historical row whose hash is NULL, returns HTTP 409
`IDEMPOTENCY_CONFLICT`. RUNNING and FAILED duplicates retain the existing controlled
conflict behavior. The decision is made while the session row is locked, and the database
unique key remains the final concurrency guard.

## Evidence and comparison policy

FACT and COMPARISON claims must identify an allowlisted field under a concrete
`records.<index>` path and bind value, unit, trade date, entity and Evidence ID to the same
actual tool result. Values use exact Decimal comparison; percentages permit only the
explicit stored-decimal to displayed-percent conversion. Verified user-visible text is
reconstructed by the server, so unverified model numbers are never copied into the final
answer.

INFERENCE claims require Evidence and receive WARNING quality. Legacy factual drafts
without claims, unknown Evidence, wrong values/entities/dates/units/paths, mixed
calculation identities and TRAIN-as-OOS assertions fail closed. Legal entity-over-time or
independent-run comparisons retain explicit context warnings.

Limits are 16 claims per response, 8 Evidence IDs per claim and 12 structured facts per
claim, in addition to the existing token, character, byte, round and call budgets.

## Database rollout and rollback risk

Run `python -m alembic upgrade head` while Chat remains disabled. Migration 0048 adds a
nullable `request_content_hash` and canonical-format check; it deliberately leaves all
historical rows NULL. Migration 0049 only normalizes the constraint name in an environment
that applied a pre-release 0048 form and is otherwise a no-op. Neither migration rewrites
messages, Evidence or tool audits.

Do not downgrade a database containing user chat history as an ordinary rollback.
Disabling Chat is the safe runtime rollback. Any schema downgrade or history deletion
requires a separately approved backup/export and destructive maintenance procedure.

## Cancellation boundary

The total deadline and tool timeout are soft boundaries for synchronous Python. Python
work cannot be safely preempted by this implementation; if a handler returns after its
budget, the result is rejected. PostgreSQL `statement_timeout` is the hard cancellation
boundary for SQL. Deployment-level HTTP/proxy timeouts remain required.

## Verification

The following commands were executed against the final source tree:

```bash
docker run --rm -v "$PWD:/app:ro" -w /app --entrypoint python ssh-stock-app:local \
  -m pytest -p no:cacheprovider -q \
  tests/unit/test_m16_2_1_chat_reliability.py \
  tests/unit/test_m16_2_llm_orchestration.py \
  tests/unit/test_m16_1_agent_contracts.py
# 41 passed

docker compose run --rm --no-deps -v "$PWD:/app:ro" --entrypoint python backend \
  -m pytest -p no:cacheprovider -q \
  tests/integration/test_m16_2_migration.py \
  tests/integration/test_m16_2_agent_chat.py \
  tests/integration/test_m16_1_1_agent_reliability.py
# 12 passed, 4 dependency deprecation warnings

docker run --rm -v "$PWD:/app:ro" -w /app --entrypoint python ssh-stock-app:local \
  -m ruff check --no-cache backend tests migrations scripts
# All checks passed

docker compose run --rm --no-deps -v "$PWD:/app:ro" --entrypoint python backend \
  -m alembic upgrade head
docker compose run --rm --no-deps -v "$PWD:/app:ro" --entrypoint python backend \
  -m alembic current
docker compose run --rm --no-deps -v "$PWD:/app:ro" --entrypoint python backend \
  -m alembic heads
# current == heads == 0049_m16_2_1_hash_name

docker compose run --rm --no-deps -v "$PWD:/app:ro" --entrypoint python backend \
  -m pytest -p no:cacheprovider -q
# 1034 passed, 5 dependency deprecation warnings in 658.60s
```

## Main changed files

- Deadline/config/domain: `backend/app/core/agent_db.py`,
  `backend/app/core/agent_llm_config.py`, `backend/app/domain/agent/chat.py`.
- Chat orchestration/evidence: `backend/app/services/agent/chat/application.py`,
  `orchestrator.py`, `evidence_compiler.py`, `comparison_policy.py`,
  `request_identity.py`.
- Tool execution/persistence: `backend/app/services/agent/application.py`,
  `backend/app/repositories/agent_chat.py`, `backend/app/models/agent_chat.py`.
- Schema: migrations 0048 and 0049.
- Regression coverage: M16.1/M16.2 unit and integration tests plus
  `tests/unit/test_m16_2_1_chat_reliability.py`.
