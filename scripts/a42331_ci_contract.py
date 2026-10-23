"""Narrow reviewed test-job exception; historical manifests and release gates stay frozen."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

BASELINE = '7bc29740948742bebee65e2e2a5814553fc41934'
# Exact reviewed test job, including all old commands, coverage, timeouts and new evidence steps.
REVIEWED_TEST_JOB = '701504087872320ae808129f1526cac6bebdda2198aea320048444cd024e5a9a'


def normalize_test_job(job):
    root = Path(__file__).resolve().parents[1]
    before = yaml.safe_load(subprocess.check_output(
        ['git','show',BASELINE+':.github/workflows/ci.yml'],cwd=root))['jobs']['test']
    encoded = json.dumps(job,sort_keys=True,separators=(',',':')).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    if digest != REVIEWED_TEST_JOB:
        raise RuntimeError('A42331_UNREVIEWED_CI_TEST_JOB')
    return copy.deepcopy(before)
