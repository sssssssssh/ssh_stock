# A42362 Method Decisions and STOP

## ADR-01: Target Session GUC Proof

Decision: METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION. No seventeenth query, no modified
allowlist/template, no new preparation, no extra connection counted as the target session.

PostgreSQL pg_settings/SHOW reflects the querying session. An Owner connection's view is
not the probe's actual transaction_read_only or statement_timeout.
libpq's reported parameter list includes default_transaction_read_only but not
statement_timeout; PQoptions reports what was requested, not actual accepted settings.
Inference: these interfaces do not supply the complete independent proof required here.
References: [PG17 settings](https://www.postgresql.org/docs/17/view-pg-settings.html),
[PG17 libpq status](https://www.postgresql.org/docs/17/libpq-status.html).

A future protocol decision could approve changing a fixed projection template to return
target-session current_setting values without increasing the total16 statements. That
still changes frozen SQL/allowlist and is NOT approved or implemented in this task.
The current required method raises before worker credential RPC/connect/probe, and before
legacy Controller actually creates a fixture. Configured settings are labelled
CONFIGURED_NOT_INDEPENDENTLY_OBSERVED, never SESSION_GUC_VERIFIED.

## ADR-02: Scope Termination

A reaped leader is not the whole scope. Watchdog now checks visible group emptiness.
A new outer bounded helper returns/raises TERMINATION_NOT_PROVEN when a descendant remains,
and never signals an already-reaped/reusable group. First failure and cleanup failure
are separate. Group emptiness still cannot prove that no descendant escaped with setsid.

Nondelegated root-manager cgroup ownership, pinned directory/kill FDs, distinct Supervisor
and Worker identities and FD isolation remain SOURCE UNRESOLVED. The old Deployment
requires equal Supervisor/Worker UID, which cannot be presented as privilege separation.
No cgroup/root-manager proof is fabricated by an offline test or systemd unit.

## ADR-03: Independent Absence and Metrics

Rootless Podman visibility under a different E UID needs independently reviewed readonly
namespace/storage delegation. E cannot infer ABSENT from its own empty namespace or C JSON.
Secret labels/name/ID alone may not prove creation epoch; inspect metadata support must be
pinned for the installed Podman version. Reference:
[Podman secret inspect](https://docs.podman.io/en/latest/markdown/podman-secret-inspect.1.html).
Until concrete audit storage/delegation exists, E composition remains unconfigured.

CPU stays METRIC_UNAVAILABLE absent bidirectional PID/start/namespace proof. Cached plan
structure and actual prepared/Observer long-window feasibility remain NOT_PROVEN.
G2 total8 and G3 unauthorized are untouched. No metric is replaced with zero.

## Stop Result

This is a correct blocked method outcome, NOT a full engineering completion.
Further Owner/C/E/D source integration and independently reviewed protocol/identity decisions
are required. Neither keys supplied later nor Git/CI green alone may bypass these gaps.
