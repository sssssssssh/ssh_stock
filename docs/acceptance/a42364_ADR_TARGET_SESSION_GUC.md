# D3: TARGET_SESSION_GUC

NOT_APPROVED. **Approve / Reject / Need changes** unselected.
Choices: FOUR_SLOT_V3, or KEEP_CLOSED. KEEP_CLOSED is a recorded decision to deny,
not a v3 execution capability. Legacy session_method() remains unconditional DENY.

## Exact Candidate Protocol

Version a42364.target-session.v3. Exactly16 SQL, six I4, six I8 and four projections
at slots6/8/14/16, per-query100ms, total2s, max8rows, prepare_threshold5, natural GC;
no forced prepare, seventeenth query or extra warmup. G2 effective warmups TOTAL8
remain pending. G3 128/64 remains NOT_AUTHORIZED.
Projection byte length406; SHA256 `2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56`.

```sql
SELECT current_setting('statement_timeout') AS statement_timeout, current_setting('transaction_read_only')::boolean AS read_only, p.name,p.parameter_types::oid[],p.from_sql,p.generic_plans,p.custom_plans FROM (SELECT 1) AS singleton LEFT JOIN LATERAL (SELECT name,parameter_types,from_sql,generic_plans,custom_plans FROM pg_catalog.pg_prepared_statements ORDER BY name LIMIT 8) AS p ON true ORDER BY p.name
```

Output OIDs: 25,16,25,1028,16,20,20. Raw driver/wire/parameter hashes:
- Slot 1 I4: driver=91211cff1306a91b34112309539433af1641650fa4ae6b56a154cf33bfed6f71, wire=6f662bb7e0eb66fcc5c4e37998064aa5057fb9454365205078432d8d445fe9a2, parameter_oids=[23].
- Slot 2 I4: driver=91211cff1306a91b34112309539433af1641650fa4ae6b56a154cf33bfed6f71, wire=6f662bb7e0eb66fcc5c4e37998064aa5057fb9454365205078432d8d445fe9a2, parameter_oids=[23].
- Slot 3 I4: driver=91211cff1306a91b34112309539433af1641650fa4ae6b56a154cf33bfed6f71, wire=6f662bb7e0eb66fcc5c4e37998064aa5057fb9454365205078432d8d445fe9a2, parameter_oids=[23].
- Slot 4 I4: driver=91211cff1306a91b34112309539433af1641650fa4ae6b56a154cf33bfed6f71, wire=6f662bb7e0eb66fcc5c4e37998064aa5057fb9454365205078432d8d445fe9a2, parameter_oids=[23].
- Slot 5 I4: driver=91211cff1306a91b34112309539433af1641650fa4ae6b56a154cf33bfed6f71, wire=6f662bb7e0eb66fcc5c4e37998064aa5057fb9454365205078432d8d445fe9a2, parameter_oids=[23].
- Slot 6 PROJECTION: driver=2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56, wire=2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56, parameter_oids=[].
- Slot 7 I4: driver=91211cff1306a91b34112309539433af1641650fa4ae6b56a154cf33bfed6f71, wire=6f662bb7e0eb66fcc5c4e37998064aa5057fb9454365205078432d8d445fe9a2, parameter_oids=[23].
- Slot 8 PROJECTION: driver=2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56, wire=2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56, parameter_oids=[].
- Slot 9 I8: driver=20fb6e485e2388fe7d524bc79cc7219cc016ba0f21c32084662e74b1e35b231b, wire=47e6e307a1e0fe22b23f23a7e2a35174b2c52965b190028f9797d42d02e4b274, parameter_oids=[20].
- Slot 10 I8: driver=20fb6e485e2388fe7d524bc79cc7219cc016ba0f21c32084662e74b1e35b231b, wire=47e6e307a1e0fe22b23f23a7e2a35174b2c52965b190028f9797d42d02e4b274, parameter_oids=[20].
- Slot 11 I8: driver=20fb6e485e2388fe7d524bc79cc7219cc016ba0f21c32084662e74b1e35b231b, wire=47e6e307a1e0fe22b23f23a7e2a35174b2c52965b190028f9797d42d02e4b274, parameter_oids=[20].
- Slot 12 I8: driver=20fb6e485e2388fe7d524bc79cc7219cc016ba0f21c32084662e74b1e35b231b, wire=47e6e307a1e0fe22b23f23a7e2a35174b2c52965b190028f9797d42d02e4b274, parameter_oids=[20].
- Slot 13 I8: driver=20fb6e485e2388fe7d524bc79cc7219cc016ba0f21c32084662e74b1e35b231b, wire=47e6e307a1e0fe22b23f23a7e2a35174b2c52965b190028f9797d42d02e4b274, parameter_oids=[20].
- Slot 14 PROJECTION: driver=2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56, wire=2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56, parameter_oids=[].
- Slot 15 I8: driver=20fb6e485e2388fe7d524bc79cc7219cc016ba0f21c32084662e74b1e35b231b, wire=47e6e307a1e0fe22b23f23a7e2a35174b2c52965b190028f9797d42d02e4b274, parameter_oids=[20].
- Slot 16 PROJECTION: driver=2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56, wire=2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56, parameter_oids=[].

CandidateSessionExecutor requires a real pinned psycopg3.3.4 connection, actual
probe role/database/private socket, stable backend PID/start/generation/namespace
before/after, correct prepared continuity and actual projection output OIDs.
PinnedSessionSource obtains independent Owner pg_stat_activity identity, not
Owner SHOW settings. Owner audit query SHA256:
`e9cd640000016bc4b4116648f30e71602e3d3b08feeb97375b38e1ee1b4e2ee7`, exactly2queries,100ms each,
outside the16 probe queries. Its independent connection budgeting/provisioner
remains a SOURCE gap; never reuse/reset bootstrap slots. Pure parser/model results
always target_session_settings_observed=false and qualifies=false.

PostgreSQL does not automatically send arbitrary GUCs as ParameterStatus;
[protocol flow](https://www.postgresql.org/docs/17/protocol-flow.html) is not a
substitute for an actual same-session projection.

## Signing, Compatibility, Recovery and Rollback

CandidateDecision/SignedDecision strict schema in protocol_decision.py:
kind TARGET_SESSION_GUC, choice FOUR_SLOT_V3, version
a42364.external-decision.v3, canonical complete Scope and proposal/install/image
hashes, issued/expires<=300s, nonce and disposition; exactly OWNER and
SAFETY_PLATFORM signatures. Root FD custody and current A registry revocation
check are mandatory. Source/allowlist/schema hashes are pinned in eighth overlay;
old allowlist/templates and historical grant identities remain original bytes.
Old token/new protocol, missing authority, wrong backend/OID/budget/GC/role, replay
or changed installation all deny. New protocol is not backward-compatible.
Separate G1_L2_EXECUTION consumed-once permission is also required.
Protocol denial means SQL0. Failure after execution begins has no retry/refund.
Rollback closes candidate selection and retains old DENY; no evidence rewriting.

HIGH risk until independent signatures, installed session source and real
same-backend experiment are validated. No real session or GUC was observed here.

| Independent reviewer | Disposition | kid / external record | Signature / time |
|---|---|---|---|
| Project OWNER | Unselected | NOT_PROVIDED | NOT_SIGNED |
| SAFETY_PLATFORM | Unselected | NOT_PROVIDED | NOT_SIGNED |
