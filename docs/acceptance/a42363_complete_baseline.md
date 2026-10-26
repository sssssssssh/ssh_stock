# A42363 complete-fix baseline and evidence policy

Baseline / fetched origin/master: `d31b07a4e33d50ac00ade3e1eff60e091fe78041`.
Initial working tree was clean on master. Read PRD, design, PROJECT_RULES, README,
AGENTS and the Complete Fix taskbook before editing. `git fetch origin master`
returned the same baseline; no branch switch or destructive update was performed.

The sixth overlay registers individual files in a42363_complete_overlay_manifest.json.
All five historical manifests and each historical closing commit's pinned blobs are
verified independently. Only the new COMPLETE_MANIFEST_SHA literal is normalized.
Full HEAD FD walk, NUL/Unicode/no-follow/hidden-index/race checks remain inherited.
Two historical path assertions gain one exact layer: their old byte checks and case
counts remain, with additional new-HEAD pins. No production, workflow, dependency,
probe SQL, authorization, previous manifest or SQL003 bytes are changed.

Actual initial run: new complete-fix regression file, **13 failed /0 passed /0.17s**,
exit1, `.codex_tmp/a42363-complete-red.xml`. Five failures concern missing identity
APIs and three missing lifecycle/RPC APIs; concrete existing defects include volume
API identity confusion, missing between-round ledger check, guardian launched too
late and wrong Owner receipt phase accepted. These failures are not physical tests.

Later publication regression actually failed once: final TERMINATED was committed
before publisher failure, **1 failed /0.11s**. Fixed by TERMINATION_PROVEN followed
by publication and only then TERMINATED. Raw file: complete-publication-red.xml.
The first expanded L1 run failed13/64passed due to a bad fixture: its approval-row
second column1 meant REVOKED. Corrected the model to match actual SQL's boolean,
without changing production revocation checks. A later forged phase exposed an
unclassified missing-source exception; source read errors now fail with a safe code.
An exploratory revocation fixture omitted required revision/expiry and failed schema
validation; this was a test fixture mistake, not an expiry defect or a source fix.
Those raw failures remain local. Never present a fixture correction as a product RED.

Targeted new + existing A42363 contracts/processes: **230 passed /7.58s**, before the
remaining documentation/freeze steps. Suites at different times are not additive.
Final tests and same-SHA ordinary CI are reported in the external delivery receipt,
after the final commit exists. No future CI IDs/results are prefilled in frozen files.
No local `.env`, PG17/Podman/systemd/cgroup deployment, cloud or business DB was used.

State remains ENGINEERING_BLOCKED. This baseline record is not a claim that W00–W11
or AT01–AT60 physically passed. Preserve G1 SQL0, G2 pending8 and G3 unauthorized.
