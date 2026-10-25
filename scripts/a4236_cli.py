"""Static/offline CLI only. Live flags, approval claims and events never open a connection."""

import json
import os
import sys
from pathlib import Path

from scripts.a4236_g1_harness_contract import Fault, Status, require


def expected_from_git():
    from scripts import a4235_capability_guard as guard
    from scripts.a4236_mock import context

    return context(
        identity=guard.expected_identity(
            run_id=os.environ.get("GITHUB_RUN_ID", "local"),
            attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
        ),
        overlay=guard.overlay_fingerprint(),
        kind="OFFLINE_DESIGN",
    )


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        # All actual-execution requests reject BEFORE inspecting tokens, env or files.
        require(
            (len(args) == 3 and args[:2] == ["--check-static", "--target-sha"])
            or (len(args) == 2 and args[0] == "--directory" and not args[1].startswith("--")),
            "A4236_G1_NOT_RUN_NOT_AUTHORIZED",
        )
        if args[0] == "--check-static":
            from scripts import a4235_capability_guard as guard

            guard.check_static(args[2])
            value = dict(
                **Status().model_dump(),
                scope="STATIC_ONLY",
                context=expected_from_git().model_dump(),
            )
            code = 2
        else:
            from scripts.a4236_evidence import review_bundle

            value = review_bundle(Path(args[1]), expected_from_git())
            code = 3
        print(json.dumps(value, sort_keys=True, allow_nan=False))
        return code
    except BaseException as error:
        code = error.code if isinstance(error, Fault) else "A4236_OFFLINE_REVIEW_REJECTED"
        print(json.dumps(dict(**Status().model_dump(), first_error=code), sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
