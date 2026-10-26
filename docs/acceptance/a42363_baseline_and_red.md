# A42363 baseline and execution contract

Baseline: 5acc2e71c43cc77172e9caca103cc843c04d704d, clean master, fast-forwarded
from origin/master before development. Historical CI40276286848 is not this delivery's CI.

W00 registers ten missing implementation contracts in test_a42363_red.py. They are
engineering gaps, not vulnerabilities in the intentionally denied default entrypoint.
Actual initial RED: 10 failed, 0 passed, exit1, 0.08s; JUnit a42363-red.xml.
The RED run is preserved locally with its actual exit code and JUnit. Subsequent
behavioral tests must exercise these implementations, not merely their names.

Authorized scope: new scripts/a42363_{contract,stores,owner,resources,absence,supervisor,
services,review,source_guard}.py; new tests/unit/test_a42363_{red,contracts,source_guard}.py;
new tests/integration_offline/test_a42363_process.py; dedicated reviewed SQL003;
new acceptance documents named in the taskbook and exact overlay manifest;
append-only updates to the four Markdown authorities. Precise compatibility extensions
are limited to a42361_source_guard.py, a4235_capability_guard.py and the two old exact-path
tests. Their historical contents remain independently pinned, not exempt directories.

No production modules, dependencies, workflows, old manifests or SQL/probe templates
may change. Local commits are staged; one final push after validation. No G1/PG17/
Podman/systemd/cgroup installation or execution. Linux L1 local processes/FD/files only.
Session-method approval cannot be inferred from this development authorization.
