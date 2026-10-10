# M16 Read-only Research Agent Architecture

## Runtime boundary

The runtime is `tools_only` and `llm_enabled=false`. The API reuses the existing
session-cookie authentication. Because the current product has one bootstrap user and
no roles, access means authenticated single-tenant administrator access.

`POST /api/v1/agent/tools/execute` accepts exactly one tool call. It uses a dedicated
PostgreSQL `READ ONLY` transaction, a local statement timeout, and unconditional
rollback. No Agent endpoint creates `job_run`, starts calculations, or commits data.

## Explicit read-only registry

| Tool | Input | Resource limit | Empty/not-ready behavior |
| --- | --- | --- | --- |
| `data.coverage` | `start_date`, `end_date` | 366 calendar days; 32 nested datasets | `DATA_INCOMPLETE` |
| `market.snapshot` | optional `trade_date` | 1 record | HTTP 503 `NOT_READY` |
| `sector.top` | optional `trade_date`, `limit` | 20 | `EMPTY_RESULT` |
| `theme.top` | optional `trade_date`, `limit` | 20 | `SOURCE_DEGRADED` / `EMPTY_RESULT` |
| `opportunity.list` | optional `trade_date`, controlled `stage`, `limit` | 30 | `EMPTY_RESULT` |
| `backtest.summary` | exact `run_id` | 1 | `NOT_FOUND` / `NOT_READY` |
| `performance.summary` | exactly one of `run_id`, `report_id` | 1 | `NOT_FOUND` / `NOT_READY` |
| `walk_forward.summary` | exact `study_id`, `validation_id` | 1 | `NOT_FOUND` / `NOT_READY` |

`max_records` in the catalog applies only to the top-level `records` array. Evidence,
warnings and declared nested lists have separate positive limits; the final serialized
payload is limited to 64 KiB. All schemas reject unknown fields. The registry is explicit;
reflection, dynamic import,
arbitrary SQL, arbitrary URL, Python expression, filesystem path and shell inputs are
not accepted. The default builder returns exactly the published eight tools, while the
registry validator itself checks unique legal names, versions, allowed layers, read-only
handlers and positive budgets instead of treating a hard-coded count as a safety boundary.

## API examples

```json
POST /api/v1/agent/tools/execute
{
  "tool_name": "sector.top",
  "input": {"trade_date": "2026-08-31", "limit": 5},
  "request_id": "research-20260831-1"
}
```

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "tool_name": "sector.top",
    "tool_version": "1.0",
    "status": "READY",
    "as_of_date": "2026-08-31",
    "identity": {"calc_version": "sector_v1", "config_hash": "..."},
    "records": [{"sector_id": 1, "sector_name": "示例", "heat_score": "82.5"}],
    "evidence": [{"evidence_id": "...", "layer": "FACTOR_TREND"}],
    "warnings": [],
    "readiness": {"ready": true, "code": "READY", "details": {}}
  },
  "meta": {"request_id": "research-20260831-1"}
}
```

`GET /api/v1/agent/tools` returns the eight JSON schemas. `GET /api/v1/agent/status`
returns `agent_mode=tools_only`, registry version, the actual registry length, read-only
mode, LLM-disabled state, and the hard per-SQL statement timeout metadata.

## Resource and timeout semantics

`ToolSpec.timeout_seconds` is a monotonic end-to-end soft budget. A synchronous handler
that returns after that budget is rejected with `TOOL_TIMEOUT`, but the check does not
claim to preempt Python or recover resources already consumed. No timeout worker thread is
created. PostgreSQL independently enforces a transaction-local hard timeout for each SQL
statement and SQLSTATE `57014` maps to `SQL_STATEMENT_TIMEOUT`. Reverse proxy/application
server HTTP timeouts remain the outer hard boundary.

The application checks top-level records, Evidence references, warnings and named nested
lists before serialization. A structural count violation is `RESOURCE_LIMIT_EXCEEDED`;
only the final canonical JSON byte limit uses `OUTPUT_LIMIT_EXCEEDED`. Coverage queries
first fetch at most 33 distinct dataset names, fail closed above 32, and only then build
the aggregate, so no truncation can be mistaken for a complete statistic.

### Deterministic fixture examples

The catalog endpoint is the authoritative input JSON Schema. These bounded fixture
examples show the corresponding record shape; every response also includes identity,
evidence, warnings, and readiness.

| Tool | Example input | Example output fields |
| --- | --- | --- |
| `data.coverage` | `start_date=2026-08-01, end_date=2026-08-31` | `quality_status=PASS, dataset_coverage=[...], latest_trading_date=2026-08-31` |
| `market.snapshot` | `trade_date=2026-08-31` | `regime=RISK_ON, market_score=80.5, breadth={...}, liquidity={...}` |
| `sector.top` | `trade_date=2026-08-31, limit=5` | `sector_code=801010.SI, heat_score=82.5, momentum={...}, lifecycle=MAIN_UP` |
| `theme.top` | `trade_date=2026-08-31, limit=5` | `theme_code=885001.TI, source_coverage=1, member_snapshot_date=2026-08-31` |
| `opportunity.list` | `trade_date=2026-08-31, stage=RIGHT_SIDE, limit=10` | `ts_code=000001.SZ, stage=RIGHT_SIDE, score=88, reason_codes=[]` |
| `backtest.summary` | `run_id=11111111-1111-1111-1111-111111111111` | `status=SUCCESS, latest_nav=1.05, source_identity={...}` |
| `performance.summary` | `report_id=22222222-2222-2222-2222-222222222222` | `report_ids, performance, risk, trade, period` |
| `walk_forward.summary` | `study_id=33333333-3333-3333-3333-333333333333, validation_id=44444444-4444-4444-4444-444444444444` | `result_stage=OOS, oos_sample, returns, parameter_switching` |

Values above are fixtures, not claims about production data.

## Identity, PIT and evidence

- Market and sector reads require current calculation version plus analysis strategy
  hash. Theme and Opportunity reuse the existing identity filter helpers.
- If rows exist for the requested date only under another identity, execution fails with
  `SOURCE_IDENTITY_MISMATCH`; it never silently mixes versions.
- Historical Theme output uses `theme_factor_daily.member_snapshot_date` already frozen
  by the calculation. It never joins current Theme members into a historical answer.
- Same-day Opportunity records expose no forward-return fields.
- M14 and Walk-forward evidence uses stored report UUIDs and stored config/source hashes,
  never runtime YAML reconstructed as historical identity.
- New Evidence uses `evidence_version=v2`. `source_record_id` remains a business locator;
  `evidence_id` is SHA-256 over canonical source identity, optional real `calc_run_id`,
  quality limitations and a deterministic `content_hash` of the complete returned fact.
  Request IDs and current time are excluded.

`EvidenceRef` keeps all V1 fields and compatibly adds `evidence_version`, `calc_run_id` and
`content_hash`. Its fields are: `evidence_id`, `layer`, `source_type`, `entity_id`, optional
`trade_date`, `source_record_id`, `calc_version`, `algo_version`, `config_hash`, `source_hash`,
`report_id`, `observed_at`, `quality_status`, and `limitations`. Decimal and float-derived
precision values serialize as decimal strings. Missing metrics remain `null` and add a
warning where the missing value changes interpretation.

`performance.summary` first selects one unambiguous Performance report and then applies
the shared read-only M14 exact-bundle validator. Performance, Risk and Trade are required;
Period remains optional for this overview contract. Missing Period adds
`DATA_UNAVAILABLE:period_report`; an existing Period must match the same owner, status,
date scope and source identity.

## Errors

| Code | HTTP | Meaning |
| --- | --- | --- |
| `INVALID_TOOL` | 422 | Tool is not in the fixed registry |
| `INVALID_ARGUMENT` | 422 | Strict schema, range, selector or request-size failure |
| `UNAUTHORIZED` | 401 | Existing session validation rejected the Agent request |
| `NOT_FOUND` | 404 | Exact run/report/study owner not found |
| `NOT_READY` | 503 | Required persisted result is not ready |
| `SOURCE_IDENTITY_MISMATCH` | 409 | Requested date/report exists under incompatible identity |
| `DATA_INCOMPLETE` | 200 status | Coverage result is available but incomplete |
| `RESOURCE_LIMIT_EXCEEDED` | 422 | Record, Evidence, warning or nested-list count exceeded |
| `OUTPUT_LIMIT_EXCEEDED` | 422 | Final serialized response exceeds 64 KiB |
| `TOOL_TIMEOUT` | 504 | Handler returned after its soft end-to-end budget |
| `SQL_STATEMENT_TIMEOUT` | 504 | PostgreSQL canceled one SQL statement at its hard timeout |
| `INTERNAL_ERROR` | 500 | Unexpected handler failure; details are not exposed |

Audit logs contain only request ID, hashed user identity, tool/version, duration, status,
safe error code, record count and evidence count. Success, validation failure, AgentError,
database timeout and unknown exceptions all emit one audit event. Tokens, cookies, request
input, SQL/DSN, prompts and result bodies are not logged.

## M16.2 evidence-backed chat runtime

M16.2 adds an optional synchronous chat layer in front of the unchanged M16.1 registry.
It is disabled by default (`mode=tools_only`, `llm_enabled=false`), so service startup and
the three original Agent endpoints never require a model key. Enabling it requires
`mode=llm_chat`, `llm_enabled=true`, an OpenAI-compatible model configuration and a key in
the environment variable named by `api_key_env`; the key is never stored in YAML, chat
rows, tool audit rows or logs.

The provider boundary accepts typed `ChatMessage`, `LLMTool`, `ToolCall`, `LLMResponse`
and usage DTOs. The production adapter calls Chat Completions, while tests use the
deterministic `FakeLLMProvider`. Authentication, rate limiting, timeout, unsupported tool
calling and invalid response failures map to safe local error codes without exposing the
remote URL, response body or credential.

### Controlled orchestration

The model sees JSON Schema only for enabled, read-only registry entries. Calls remain
serial and preserve model order. Unknown/disabled tools, invalid arguments and duplicate
call IDs fail closed. Identical calls in one round execute once, but every model call ID
receives a Tool Role response and an audit row; reused failures remain failures.

Hard bounds cover provider timeout, overall monotonic deadline, tool rounds, per-round and
total tool calls, context messages, user/answer length and model output tokens. No network
wait holds a database transaction. Every actual tool execution opens a new Agent
`READ ONLY` transaction and always rolls it back; chat state and audit metadata use the
normal write session in separate short commits.

Tool results are untrusted data. The system prompt forbids treating user/database text as
instructions, inventing facts, promising returns or claiming trades. Final model output
must be structured JSON. `EvidenceCompiler` accepts citations only when the ID exists in
the current turn's real tool output and the evidence quality is not `ERROR`; it assigns
display markers server-side and propagates readiness, quality, mixed-date and identity
warnings. Missing valid evidence produces `INSUFFICIENT_EVIDENCE`, not model-filled data.

### Persistence and API

Migration `0046_m16_2_agent_chat` adds owner-scoped session, message, turn and compact
tool-call audit tables. It stores no raw tool payload. A partial unique index allows only
one `RUNNING` turn per session; `(session_id, request_id)` is the idempotency key. A
completed retry returns the persisted answer, while running or failed duplicates return a
conflict. Context is limited to the most recent configured messages and reports
`CONTEXT_TRUNCATED` when older history is omitted.

Authenticated endpoints are:

- `POST /api/v1/agent/chats`
- `GET /api/v1/agent/chats`
- `GET /api/v1/agent/chats/{chat_id}`
- `POST /api/v1/agent/chats/{chat_id}/messages`
- `DELETE /api/v1/agent/chats/{chat_id}` (soft archive)

Cross-owner reads return 404. Chat is synchronous in M16.2; streaming, tenant RBAC,
retention automation, arbitrary tools, autonomous jobs, web retrieval, strategy mutation
and broker actions remain out of scope.

### Operations and rollback

The safe rollout is: keep Chat disabled, run `alembic upgrade head`, verify the original
status/catalog/execute endpoints, configure the key in the deployment environment, then
enable `llm_chat`. Disabling Chat is an immediate configuration rollback and preserves
history. Migration downgrade is intentionally refused while any chat history exists;
export and explicitly remove that history under an approved destructive procedure before
rolling the schema back. `0047_m16_2_constraint_names` is an idempotent, data-preserving
closeout for environments that applied a pre-release 0046 draft with duplicated CHECK
constraint prefixes; it is a no-op after the final canonical 0046.
