from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("filename", ["ci.yml", "publication-v13.yml", "ab-read-a4-baseline.yml"])
def test_hidden_synthetic_evidence_uploads_are_explicit(filename):
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / filename).read_text())
    hidden = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if not step.get("uses", "").startswith("actions/upload-artifact@"):
                continue
            options = step["with"]
            paths = options["path"].splitlines()
            if not any(".codex_tmp/" in path for path in paths):
                continue
            hidden.append(options["name"])
            assert options.get("include-hidden-files") is True, options["name"]
            # Only explicit synthetic evidence, never a broad repository upload.
            assert all(path.startswith(".codex_tmp/") for path in paths)
            assert all(".env" not in path and ".." not in path for path in paths)
            assert not step.get("continue-on-error", False)
            if options["name"].startswith(("v14-", "publication-v13-")):
                assert options["if-no-files-found"] == "error"
    assert hidden
