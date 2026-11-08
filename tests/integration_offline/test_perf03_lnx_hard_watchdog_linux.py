"""Linux-only fixed Mock processes. No PG fixtures, business settings or network."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from scripts import perf03_lnx_hard_watchdog as w

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='LINUX_VERIFICATION_PENDING')
ROOT = Path(__file__).resolve().parents[2]


def invoke(scenario):
    command = [sys.executable, '-I', '-S', str(ROOT/'scripts/perf03_lnx_hard_watchdog.py'),
               '--mock', '--scenario', scenario, '--timeout-ms', '500']
    process = subprocess.Popen(command, shell=False, env=w.ENV.copy(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=4)
    except subprocess.TimeoutExpired:
        # Only our exact driver handle. Never scan/signal an unverified actor PID.
        process.kill()
        process.wait(timeout=.5)
        pytest.exit('HARD_MOCK_EXTERNAL_TIMEOUT_CLEANUP_UNCERTAIN', returncode=1)
    assert not stderr and len(stdout) <= w.MAX_BYTES + 1
    result = json.loads(stdout)
    if result['phase'] == 'CLEANUP_UNCERTAIN':
        pytest.exit('HARD_MOCK_RESOURCE_CLEANUP_UNCERTAIN', returncode=1)
    spec = w.request(scenario, run_id=result['run_id'], timeout_ms=500)
    w.validate_receipt(result, spec)
    assert result['termination'] == 'TERMINATION_CONFIRMED'
    assert result['ownership_checked']
    assert result['actor_pid'] == result['actor_pgid'] > 1
    # Signal 0 probes ONLY this known group. Never reuse it as a kill target.
    with pytest.raises(ProcessLookupError):
        os.killpg(result['actor_pgid'], 0)
    assert result['REAL_MEASUREMENT'] is False
    assert result['AC05_STATUS'] == result['R1_STATUS'] == 'PARTIAL'
    assert result['PERFORMANCE_ELIGIBILITY'] == 'NOT_CLAIMED'
    assert not any(result['authorization'].values())
    assert result['not_proven'] == w.NOT_PROVEN
    assert b'postgresql' not in stdout and b'/Users/' not in stdout and b'/home/' not in stdout
    return process.returncode, result


def test_linux_fixed_success_requires_exit_and_os_group_confirmation():
    code, result = invoke('success')
    assert code == 0 and result['phase'] == 'MOCK_COMPLETE'
    assert result['actor_exit_code'] == 0 and result['first_failure'] is None
    assert result['signals'] == [] and not result['deadline_observed']


@pytest.mark.parametrize('scenario', ['block_fifo_open', 'block_popen_simulated',
    'block_fsync_simulated', 'block_prefix_write_simulated', 'block_read_simulated',
    'block_link_simulated', 'block_close_simulated', 'ignore_term', 'late_success'])
def test_linux_blocked_actor_deadline_is_independent_and_reaped(scenario):
    code, result = invoke(scenario)
    assert code == 2 and result['phase'] == 'MOCK_TIMED_OUT'
    assert result['first_failure'] == 'HARD_MOCK_DEADLINE'
    assert result['deadline_observed'] and result['root_elapsed_seconds'] >= .5
    assert result['signals'][0] == 'TERM'
    if scenario in {'ignore_term', 'late_success'}:
        assert result['signals'] == ['TERM', 'KILL']
        assert result['actor_exit_code'] == -signal.SIGKILL
    else:
        assert result['actor_exit_code'] == -signal.SIGTERM
    if scenario == 'block_fifo_open':
        assert result['blocking_kind'] == 'ACTUAL_LINUX_BLOCKING_SYSCALL'
        assert result['fifo_block_observed']  # Owned /proc PID wchan=wait_for_partner evidence.
    elif scenario.startswith('block_'):
        assert result['blocking_kind'] == 'SIMULATED_BLOCKING'


def test_linux_same_group_child_is_reaped_by_actor_before_group_confirmation():
    code, result = invoke('child_same_group')
    assert code == 2 and result['phase'] == 'MOCK_TIMED_OUT'
    assert result['child_seen'] and result['child_reaped']
    assert result['signals'] == ['TERM']
    assert result['actor_exit_code'] == 0  # Late cooperative close is NOT task success.
    assert result['first_failure'] == 'HARD_MOCK_DEADLINE'


@pytest.mark.parametrize('scenario,first', [('nonzero', 'HARD_MOCK_EXIT'),
    ('bad_receipt', 'HARD_MOCK_PROTOCOL'), ('missing_receipt', 'HARD_MOCK_MISSING_RECEIPT')])
def test_linux_bad_or_missing_receipt_and_nonzero_never_pass(scenario, first):
    code, result = invoke(scenario)
    assert code == 2 and result['phase'] == 'MOCK_FAILED'
    assert result['first_failure'] == first
    if scenario == 'nonzero':
        assert result['actor_exit_code'] == 7


def test_linux_fifo_reference_blocks_without_watchdog_and_owned_term_reaps():
    """Reference RED condition: FIFO open has no writer and cannot finish itself."""
    spec = w.request('block_fifo_open')
    with tempfile.TemporaryDirectory(prefix='perf03_fifo_reference_') as parent:
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        read_fd, write_fd = os.pipe()
        command = [sys.executable, '-I', '-S', str(ROOT/'scripts/perf03_lnx_hard_mock_actor.py'),
            '--mock', '--run-id', spec['run_id'], '--scenario', spec['scenario'],
            '--timeout-ms', '500', '--pipe-fd', str(write_fd),
            '--directory-fd', str(directory_fd)]
        actor = None
        try:
            actor = subprocess.Popen(command, shell=False, env=w.ENV.copy(),
                pass_fds=(write_fd, directory_fd), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            with pytest.raises(subprocess.TimeoutExpired):
                actor.wait(timeout=.15)
            deadline = time.monotonic() + .5
            observed = False
            while time.monotonic() < deadline:
                observed = Path('/proc', str(actor.pid), 'wchan').read_text().strip() == \
                    'wait_for_partner'
                if observed:
                    break
                time.sleep(.002)
            assert observed
        finally:
            if actor is not None:
                # wait(timeout) above has not reaped a live actor: retain exact ownership.
                if actor.returncode is None:
                    assert os.getpgid(actor.pid) == os.getsid(actor.pid) == actor.pid
                    os.killpg(actor.pid, signal.SIGTERM)
                    try:
                        actor.wait(timeout=.5)
                    except subprocess.TimeoutExpired:
                        pytest.exit('HARD_MOCK_REFERENCE_CLEANUP_UNCERTAIN', returncode=1)
                assert actor.returncode == -signal.SIGTERM
                with pytest.raises(ProcessLookupError):
                    os.killpg(actor.pid, 0)
            for fd in (read_fd, write_fd, directory_fd):
                os.close(fd)


@pytest.mark.parametrize('scenario,created', [('child_term_before_spawn', False),
    ('child_term_before_registration', True), ('child_term_after_spawn', True)])
def test_linux_race01_term_windows_never_claim_work_success_or_leave_child(scenario, created):
    code, result = invoke(scenario)
    assert code == 2 and result['phase'] == 'MOCK_FAILED'
    assert result['first_failure'] == 'HARD_MOCK_ACTOR_TERM'
    assert result['actor_term_requested']
    assert result['actor_exit_code'] == 0  # Actor cleanup succeeded; work did NOT.
    assert result['child_seen'] is created
    assert result['child_reaped'] is created
    assert result['child_creation'] == ('OWNED' if created else 'NOT_STARTED')
    assert result['child_exit_code'] == (-signal.SIGTERM if created else None)
    assert result['cleanup_errors'] == []
