# A42364 Capability Matrix

Overall: **PARTIAL_ENGINEERING_BLOCKED**. No physical or performance qualification.

| Capability | Source / offline evidence | Physical / unresolved |
|---|---|---|
| Image entry + native bootstrap | Implemented, source/HBA/policy mutation and compile/refusal tests | NOT_RUN_NOT_AUTHORIZED; real OCI/base/SBOM/maps/SCRAM not verified |
| Static plan + offline supply verification | Implemented fixed plan, deterministic ZIP, checksum + external-root signature API | No real image/signature bundle; checksum alone does not validate contents |
| Bootstrap accounting | Candidate12/32/30s, B persistent named slots, declared29s allocation | Global exec bridge/census incomplete; active8/12/2s still BLOCKED |
| Prebuilt alternative | Costed plan, never zero cost | Provisioning/attested single-use builder NOT_IMPLEMENTED |
| Owner fixed SQL/SCRAM | 12 fixed psycopg-safe statements, autocommit CREATE DB, raw privilege/HBA audit, actual connect adapter | Model tests not real authentication; full HBA target audit/provisioner requires further review |
| Volume disposal | Fixed-name manager, original facts, persistent attempts, ABA/mount/epoch checks | Kernel all-writer broker NOT_IMPLEMENTED; SAFE_DELETE_UNPROVEN |
| Four-resource recovery | Durable generic action keys + original creation facts | Whole-chain START/STOP global wiring incomplete; no real resources |
| E collector | RO mount/namespace/inode/hash verification and unknown-code/recheck negatives | Same-store cross-UID RO delegation provisioner missing; no physical independence proof |
| Trusted package | Strict schema, exact six-file fsync stage, entry/source FD verification, units | Default host status-only; complete factory, UID/FD lifecycle provisioning incomplete |
| Guardian | Existing kernel interfaces preserved, private controlled-child tests retained/extended | Real cgroup/pidfd/setsid/multi-UID L2 NOT_RUN |
| GUC candidate | Exact406bytes/7OID/16slots, explicit real-driver executor and same-session identity source | NOT_APPROVED; separate Owner-audit connection factory/budget incomplete; old method DENY |
| Six-domain review | Real private Unix FD/SCM_RIGHTS + SQLite MODEL stores and fresh connections | Same runner UID, not real A/B/O/C/D/E host independence |
| Source freeze | Eighth exact66-file overlay, seven historical manifests, raw/AST AT59-only exception | Ordinary same-SHA CI required; physical qualification unaffected |

Missing implementation is never represented as pending signature alone. Three
ADR dispositions are unselected; no install, signature, G1 physical or performance
credential exists. G1 SQL actual0, G2 total8 pending, G3 not authorized.
