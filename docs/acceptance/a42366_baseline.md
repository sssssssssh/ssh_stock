# A42366 Baseline and Impact Review

Baseline and origin/master: f00be6aa149d5fde145ae4137c01368a332b022f.
Worktree initially CLEAN. Taskbook: A4/G1 Real Runtime Closure, 2026-10-28.
No business environment/configuration/database is read by this work.
Existing application services are not restarted or used for validation.

## Baseline ordinary CI

All four runs below are the exact baseline, not current-source acceptance:

| Workflow | Run ID | Result |
|---|---|---|
| CI | 40568482863 | success |
| A4-1 | 40568482489 | success |
| A4-2 | 40568482703 | success |
| Publication | 40568482443 | success |

## Actual call graph and blockers

serve_installed -> build_installed_runtime -> RuntimeCoordinator -> DomainClient
-> B/O/C/D/E. InstalledWriterBroker.verify_all_writers always refuses; its runner
is None. This is a real engineering blocker, not an authorization toggle.
ControlledInstallation uses modeled owner/files/absence and is not a live server.
StagedPublisher is a callable production component but accepts eight arbitrary
observations and supervisor-owned REVIEWED; unlink precedes the PUBLISHED commit.

| Work | Classification | Baseline reproducible location |
|---|---|---|
| W01 | SOURCE_MISSING | StagedPublisher.finalize count-only validation and unlink-before-commit |
| W02 | SOURCE_MISSING | no v4 DomainClient server; old InstalledServiceHost uses another envelope |
| W03 | EXTERNAL_PLATFORM_REQUIRED | writer broker global MAC/namespace proof absent, permanent DENY |
| W04 | SOURCE_MISSING | BudgetService.native_exec is reservation-only, native census absent |
| W05 | SOURCE_MISSING | AuditConnectionFactory has no durable actual worker generation binding |
| W06 | SOURCE_MISSING | reconcile_scope calls D/C even before preparation was attempted |
| W07 | SOURCE_MISSING / EXTERNAL_PLATFORM_REQUIRED | independent Reviewer/RO mount launcher absent |
| W08 | SOURCE_MISSING / EXTERNAL_PLATFORM_REQUIRED | installed root FD/Guardian factory absent |
| W10 | APPROVAL_REQUIRED / PHYSICAL_NOT_RUN | D1/D2/D3 and separate G1 L2 unsigned |

W01/W06 RED exercises existing functions and actual unsafe acceptance/calls,
not missing imports. JUnit and SHA256 are recorded in the final test matrix.

## Versioned change boundary

Historical manifests, original tests, budgets, SQL/templates, workflow files,
infra image sources, backend/frontend/config/migrations/dependencies stay exact.
Proposed versioned overlay records each changed existing script and each new
a42366 module/test/document by exact path and SHA256. The old overlay is checked
against its original closing Git blobs, never rewritten or reused as a grant.
Only four authoritative Markdown documents may receive append-only additions.
The exact whitelist and compatibility dispatch are source review, not signatures.

No Podman/initdb/G1 SQL/cgroup/mount/image install or workflow_dispatch is run.
Physical status is NOT_RUN_NOT_AUTHORIZED; BIZ-PERF-01 remains PERFORMANCE_OPEN.
