# M16.1 Read-only Research Agent Architecture

## Runtime boundary

The runtime is `tools_only` and `llm_enabled=false`. The API reuses the existing
session-cookie authentication. Because the current product has one bootstrap user and
no roles, access means authenticated single-tenant administrator access.

`POST /api/v1/agent/tools/execute` accepts exactly one tool call. It uses a dedicated
PostgreSQL `READ ONLY` transaction, a local statement timeout, and unconditional
rollback. No Agent endpoint creates `job_run`, starts calculations, or commits data.

## Fixed registry

| Tool | Input | Hard limit | Empty/not-ready behavior |
| --- | --- | --- | --- |
| `data.coverage` | `start_date`, `end_date` | 366 calendar days | `DATA_INCOMPLETE` |
| `market.snapshot` | optional `trade_date` | 1 record | HTTP 503 `NOT_READY` |
| `sector.top` | optional `trade_date`, `limit` | 20 | `EMPTY_RESULT` |
| `theme.top` | optional `trade_date`, `limit` | 20 | `SOURCE_DEGRADED` / `EMPTY_RESULT` |
| `opportunity.list` | optional `trade_date`, controlled `stage`, `limit` | 30 | `EMPTY_RESULT` |
| `backtest.summary` | exact `run_id` | 1 | `NOT_FOUND` / `NOT_READY` |
| `performance.summary` | exactly one of `run_id`, `report_id` | 1 | `NOT_FOUND` / `NOT_READY` |
| `walk_forward.summary` | exact `study_id`, `validation_id` | 1 | `NOT_FOUND` / `NOT_READY` |

All schemas reject unknown fields. The registry is explicit; reflection, dynamic import,
arbitrary SQL, arbitrary URL, Python expression, filesystem path and shell inputs are
not accepted. The full serialized result is limited to 64 KiB.

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
returns `agent_mode=tools_only`, registry version, tool count, read-only mode and LLM
disabled state.

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
- `evidence_id` is SHA-256 over canonical source identity, entity, date and report ID.

`EvidenceRef` fields are: `evidence_id`, `layer`, `source_type`, `entity_id`, optional
`trade_date`, `source_record_id`, `calc_version`, `algo_version`, `config_hash`, `source_hash`,
`report_id`, `observed_at`, `quality_status`, and `limitations`. Decimal and float-derived
precision values serialize as decimal strings. Missing metrics remain `null` and add a
warning where the missing value changes interpretation.

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
| `OUTPUT_LIMIT_EXCEEDED` | 422 | Record count or 64 KiB response limit exceeded |
| `INTERNAL_ERROR` | 500 | Unexpected handler failure; details are not exposed |

Audit logs contain only request ID, hashed user identity, tool/version, duration, status,
record count and evidence count. Tokens, cookies, request input, prompts and result bodies
are not logged.

## M16.2 TODO

Future work may put an LLM in front of this registry only. It must consume the catalog and
serialized result contract, not ORM/session/provider objects. Prompt policy, model vendor,
conversation retention, citation rendering, tenant RBAC and model-specific safety review
remain explicitly deferred.
