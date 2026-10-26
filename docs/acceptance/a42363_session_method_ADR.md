# ADR: target session GUC and v2 proof

Decision: METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION. No execution approval has been given.
Another backend's pg_settings/SHOW does not establish the target session's GUCs.
Role defaults and libpq connection options remain CONFIGURED_NOT_INDEPENDENTLY_OBSERVED.

| Option | Probe SQL | Bytes/allowlist | Permission | Decision |
|---|---|---|---|---|
| A: include current_setting values in one existing prepared projection | still16, including4 projections | changes one frozen projection and allowlist digest | independent protocol approval | recommended for separate review, NOT enabled |
| B: non-target-session raw proof plus physical containment | no additional query | unchanged only if proof actually sufficient | independently reviewed kernel/session method | insufficient proof currently |
| C: retain unconditional method gate | zero executed | unchanged | none | current implementation |

Option A needs explicit human approval of the precise new projection text, column/OID
contract, allowlist hash, result parser, one-shot authorization and old-protocol coexistence.
This task does not supply that approval. No hidden seventeenth query, preparation or
warmup is permitted. The old sixteen-statement schedule, four projections, 100ms/2s/8-row
limits and GC behavior are byte-frozen. G2 stays total8; G3 stays128/64 NOT_AUTHORIZED.

Lease v2 contains scope/worker PID/expiry/credential FD, never a not-yet-existing
backend start. Session v2 requires actual backend PID/start, role, namespace and connection
generation after connect. Both credential release and first probe SQL remain blocked.
Owner's eight fixed initialization SQLs are separate from the probe budget, never enlarged.
Initialization/fixed runtime commands exceeding the frozen budget fail rather than retry.

Approver: project owner via a new explicit protocol decision. Rollback: retain C and
all consumed/unknown journals; do not erase history or re-enable a historical entrypoint.
Method blocking does not excuse unrelated C/E/D source gaps; see closeout for actual status.
