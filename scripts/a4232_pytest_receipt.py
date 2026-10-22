"""Pytest failure metadata without exception messages, parameters or SQL."""

import re
from pathlib import Path

from scripts.a42_artifacts import atomic, failure, header

ERRORS = []


def safe_exception(error):
    value = failure(error)
    value.pop('failure_code',None)  # Do not infer a code from arbitrary message text here.
    state = getattr(error,'a4232_sqlstate',value.get('sqlstate'))
    value['sqlstate'] = (state if isinstance(state,str)
                         and re.fullmatch(r'[A-Z0-9]{5}',state) else None)
    driver_type = getattr(error,'a4232_driver_type',None)
    if isinstance(driver_type,str) and re.fullmatch(r'[A-Za-z_]{1,80}',driver_type):
        value['driver_type'] = driver_type
    return value


def pytest_exception_interact(node, call, report):
    if call.excinfo is None:
        return
    ERRORS.append(dict(phase=getattr(report,'when','collect'),
                       exception=safe_exception(call.excinfo.value)))
    atomic(Path('.codex_tmp/a4232-contract/failures.json'),dict(
        **header('a4232-light-failures'),status='INCOMPLETE',capacity_ready=False,
        evidence_kind='DIAGNOSTIC_ONLY',failures=ERRORS))
