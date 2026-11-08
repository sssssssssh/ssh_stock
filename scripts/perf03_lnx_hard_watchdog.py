"""Linux fixed Mock actor only. No business adapter or real-experiment authority."""

import argparse
import hashlib
import json
import math
import os
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

SCHEMA = 'perf03-lnx.hard-mock.v1'
SCENARIOS = ('success', 'block_fifo_open', 'block_popen_simulated', 'block_fsync_simulated',
             'block_prefix_write_simulated', 'block_read_simulated', 'block_link_simulated',
             'block_close_simulated', 'ignore_term', 'child_same_group', 'bad_receipt',
             'nonzero', 'missing_receipt', 'late_success', 'child_term_before_spawn',
             'child_term_before_registration', 'child_term_after_spawn')
CHILD_SCENARIOS = ('child_same_group', 'child_term_before_spawn',
                   'child_term_before_registration', 'child_term_after_spawn')
STATES = ('MOCK_COMPLETE', 'MOCK_TIMED_OUT', 'MOCK_FAILED', 'WATCHDOG_UNAVAILABLE',
          'CLEANUP_UNCERTAIN')
AUTHORIZATION = dict(real_execution=False, capacity_ready=False, production_read_authorized=False)
NOT_PROVEN = ['FIRST_SPAWN', 'WATCHDOG_SYSCALLS', 'UNINTERRUPTIBLE_D_STATE', 'DURABLE_TRUST']
ROOT = Path(__file__).resolve().parent
ENV = {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'}
TERM_SECONDS = .2
KILL_SECONDS = .2
MAX_BYTES = 4096
_USED = set()


class Refused(ValueError):
    """Fixed, non-sensitive refusal only."""


def require(value, code='HARD_MOCK_CONTRACT'):
    if not value:
        raise Refused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def request(scenario='success', *, run_id=None, timeout_ms=500):
    result = dict(schema=SCHEMA, run_id=run_id if run_id is not None else
                  'SYNTHETIC_' + uuid.uuid4().hex.upper(), scenario=scenario, timeout_ms=timeout_ms)
    validate_request(result)
    return result


def validate_request(value):
    require(type(value) is dict and set(value) == {'schema', 'run_id', 'scenario', 'timeout_ms'})
    require(value['schema'] == SCHEMA)
    require(type(value['run_id']) is str and
            re.fullmatch(r'SYNTHETIC_[A-F0-9]{32}', value['run_id']) is not None)
    require(type(value['scenario']) is str and value['scenario'] in SCENARIOS)
    require(type(value['timeout_ms']) is int and 100 <= value['timeout_ms'] <= 1000)


def spec_hash(spec):
    validate_request(spec)
    return hashlib.sha256(canonical(spec)).hexdigest()


def reserve(spec):
    validate_request(spec)
    require(spec['run_id'] not in _USED and len(_USED) < 128, 'HARD_MOCK_REPLAY')
    _USED.add(spec['run_id'])


def empty_receipt(spec):
    return dict(schema=SCHEMA, run_id=spec['run_id'], spec_sha256=spec_hash(spec),
        scenario=spec['scenario'], phase='WATCHDOG_UNAVAILABLE', first_failure=None,
        failure_reason=[], cleanup_errors=[], termination='NOT_STARTED', actor_exit_code=None,
        actor_pid=None, actor_pgid=None, ownership_checked=False, child_seen=False,
        child_reaped=False, child_exit_code=None, actor_term_requested=False,
        child_creation='NOT_ASSESSED' if spec['scenario'] in CHILD_SCENARIOS else 'NOT_APPLICABLE',
        fifo_block_observed=False, deadline_observed=False,
        signals=[], root_elapsed_seconds=0.0, cleanup_elapsed_seconds=0.0,
        blocking_kind='ACTUAL_LINUX_BLOCKING_SYSCALL' if spec['scenario'] == 'block_fifo_open'
        else 'SIMULATED_BLOCKING' if spec['scenario'].startswith('block_')
        else 'FIXED_MOCK_PROTOCOL', REAL_MEASUREMENT=False, PERFORMANCE_ELIGIBILITY='NOT_CLAIMED',
        R1_STATUS='PARTIAL', AC05_STATUS='PARTIAL', authorization=AUTHORIZATION.copy(),
        not_proven=NOT_PROVEN.copy())


def fail(receipt, code, state='MOCK_FAILED'):
    require(type(code) is str and re.fullmatch(r'HARD_MOCK_[A-Z_]{1,40}', code) is not None)
    if code not in receipt['failure_reason']:
        receipt['failure_reason'].append(code)
    receipt['first_failure'] = receipt['failure_reason'][0]
    receipt['phase'] = ('MOCK_TIMED_OUT' if receipt['deadline_observed']
                        and state == 'MOCK_FAILED' else state)


def validate_receipt(value, spec):
    template = empty_receipt(spec)
    require(type(value) is dict and set(value) == set(template))
    for key in ('schema', 'run_id', 'spec_sha256', 'scenario', 'blocking_kind', 'REAL_MEASUREMENT',
                'PERFORMANCE_ELIGIBILITY', 'R1_STATUS', 'AC05_STATUS',
                'authorization', 'not_proven'):
        require(value[key] == template[key])
    require(value['REAL_MEASUREMENT'] is False and
            all(v is False for v in value['authorization'].values()))
    require(value['phase'] in STATES)
    for key in ('ownership_checked', 'child_seen', 'child_reaped', 'fifo_block_observed',
                'deadline_observed', 'actor_term_requested'):
        require(type(value[key]) is bool)
    for key in ('root_elapsed_seconds', 'cleanup_elapsed_seconds'):
        require(type(value[key]) in (float, int) and math.isfinite(value[key]) and value[key] >= 0)
    for key in ('actor_pid', 'actor_pgid'):
        require(value[key] is None or (type(value[key]) is int and value[key] > 1))
    require(value['actor_exit_code'] is None or type(value['actor_exit_code']) is int)
    require(value['child_exit_code'] is None or type(value['child_exit_code']) is int)
    require(value['child_creation'] in {'NOT_ASSESSED', 'NOT_APPLICABLE', 'NOT_STARTED',
                                      'OWNED', 'OWNERSHIP_UNCONFIRMED'})
    require(value['signals'] in ([], ['TERM'], ['TERM', 'KILL']))
    require(value['termination'] in {'NOT_STARTED', 'TERMINATION_CONFIRMED', 'NOT_CONFIRMED'})
    for key in ('failure_reason', 'cleanup_errors'):
        require(type(value[key]) is list and len(value[key]) <= 12)
        for code in value[key]:
            require(type(code) is str and re.fullmatch(r'HARD_MOCK_[A-Z_]{1,40}', code) is not None)
    first = value['failure_reason'][0] if value['failure_reason'] else None
    require(value['first_failure'] == first)
    if value['actor_pid'] is not None:
        require(value['actor_pgid'] == value['actor_pid'])
    if value['child_reaped']:
        require(value['child_seen'] and type(value['child_exit_code']) is int
                and value['child_creation'] == 'OWNED')
    if value['phase'] == 'MOCK_COMPLETE':
        require(value['first_failure'] is None and not value['cleanup_errors']
                and not value['deadline_observed'] and not value['signals']
                and not value['actor_term_requested']
                and value['child_creation'] not in {'NOT_STARTED', 'OWNERSHIP_UNCONFIRMED'}
                and value['ownership_checked'] and value['actor_pid'] is not None
                and value['actor_exit_code'] == 0
                and value['termination'] == 'TERMINATION_CONFIRMED'
                and (not value['child_seen'] or value['child_reaped']))
    elif value['phase'] == 'MOCK_TIMED_OUT':
        require(value['deadline_observed'] and value['first_failure'] == 'HARD_MOCK_DEADLINE'
                and value['termination'] == 'TERMINATION_CONFIRMED')
    elif value['phase'] == 'CLEANUP_UNCERTAIN':
        require(value['first_failure'] is not None and bool(value['cleanup_errors'])
                and value['termination'] == 'NOT_CONFIRMED')
    else:
        require(value['first_failure'] is not None)
    require(len(canonical(value)) <= MAX_BYTES)


class Messages:
    """Bounded, ordered actor claims; none is an OS cleanup confirmation."""

    def __init__(self, spec, pid):
        self.spec, self.pid = spec, pid
        self.buffer = b''
        self.total = 0
        self.events = []
        self.child_pid = None
        self.child_exit_code = None
        self.child_failure = None
        self.child_cleanup_errors = []

    def feed(self, raw):
        require(type(raw) is bytes)
        self.total += len(raw)
        require(self.total <= MAX_BYTES, 'HARD_MOCK_PROTOCOL')
        self.buffer += raw
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                def pairs(items):
                    require(len({k for k, _ in items}) == len(items), 'HARD_MOCK_PROTOCOL')
                    return dict(items)
                value = json.loads(line, object_pairs_hook=pairs)
            except (ValueError, UnicodeError, RecursionError):
                raise Refused('HARD_MOCK_PROTOCOL') from None
            require(type(value) is dict and type(value.get('event')) is str,
                    'HARD_MOCK_PROTOCOL')
            event = value['event']
            keys = {'v', 'run_id', 'spec_sha256', 'pid', 'pgid', 'event', 'child_pid'}
            if event == 'CHILD_REAPED':
                keys.add('child_exit_code')
            if event == 'CHILD_UNCONFIRMED':
                keys.update(('child_failure', 'cleanup_errors'))
            require(set(value) == keys, 'HARD_MOCK_PROTOCOL')
            require(type(value['v']) is int and value['v'] == 1 and
                    type(value['pid']) is int and type(value['pgid']) is int and
                    value['pid'] == value['pgid'] == self.pid and
                    value['run_id'] == self.spec['run_id'] and
                    value['spec_sha256'] == spec_hash(self.spec), 'HARD_MOCK_IDENTITY')
            require('DONE' not in self.events and 'CHILD_UNCONFIRMED' not in self.events,
                    'HARD_MOCK_PROTOCOL')
            if not self.events:
                expected = {'READY'}
            elif self.spec['scenario'] not in CHILD_SCENARIOS:
                expected = {'DONE'}
            elif event == 'TERM_REQUESTED':
                expected = {'TERM_REQUESTED'} if self.events[-1] in {'READY', 'CHILD'} \
                    and 'TERM_REQUESTED' not in self.events else set()
            elif 'CHILD' not in self.events and 'CHILD_NOT_STARTED' not in self.events:
                expected = {'CHILD', 'CHILD_UNCONFIRMED'}
                if 'TERM_REQUESTED' in self.events:
                    expected.add('CHILD_NOT_STARTED')
            elif self.events[-1] in {'CHILD_REAPED', 'CHILD_NOT_STARTED'}:
                expected = {'DONE'}
            else:
                expected = {'CHILD_REAPED', 'CHILD_UNCONFIRMED'}
            require(event in expected, 'HARD_MOCK_PROTOCOL')
            if event == 'CHILD':
                require(type(value['child_pid']) is int and value['child_pid'] > 1
                        and value['child_pid'] != self.pid, 'HARD_MOCK_IDENTITY')
                self.child_pid = value['child_pid']
            else:
                require(value['child_pid'] == self.child_pid, 'HARD_MOCK_IDENTITY')
            if event == 'CHILD_REAPED':
                require(type(value['child_exit_code']) is int, 'HARD_MOCK_PROTOCOL')
                self.child_exit_code = value['child_exit_code']
            if event == 'CHILD_UNCONFIRMED':
                allowed = {'HARD_MOCK_CHILD_START_UNKNOWN', 'HARD_MOCK_CHILD_IDENTITY',
                           'HARD_MOCK_CHILD_CLEANUP', 'HARD_MOCK_CHILD_BUDGET',
                           'HARD_MOCK_CHILD_EXIT_INVALID', 'HARD_MOCK_CHILD_WAIT_UNKNOWN'}
                errors = value['cleanup_errors']
                require(type(errors) is list and 1 <= len(errors) <= 6 and
                        all(type(x) is str and x in allowed for x in errors) and
                        value['child_failure'] == errors[0], 'HARD_MOCK_PROTOCOL')
                self.child_failure = value['child_failure']
                self.child_cleanup_errors = errors
            self.events.append(event)

    def finished(self):
        return not self.buffer and bool(self.events) and self.events[-1] == 'DONE'


def _exited(process):
    # Do NOT reap with poll(): retain the original PID until all group signals end.
    return os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def _bound(process):
    require(type(process.pid) is int and process.pid > 1 and process.returncode is None,
            'HARD_MOCK_OWNERSHIP')
    require(os.getpgid(process.pid) == process.pid
            and os.getsid(process.pid) == process.pid, 'HARD_MOCK_OWNERSHIP')


def _owned(process):
    _bound(process)
    require(not _exited(process), 'HARD_MOCK_OWNERSHIP')


def _drain(fd, messages):
    for _ in range(4):
        try:
            raw = os.read(fd, 1024)
        except BlockingIOError:
            return
        if not raw:
            return
        messages.feed(raw)


def _group_gone(pid):
    try:
        os.killpg(pid, 0)  # Existence probe only, never a signal to group 0/-1.
    except ProcessLookupError:
        return True
    return False


def _claims(receipt, messages):
    receipt['child_seen'] = 'CHILD' in messages.events
    receipt['child_reaped'] = 'CHILD_REAPED' in messages.events
    receipt['child_exit_code'] = messages.child_exit_code
    if 'CHILD_NOT_STARTED' in messages.events:
        receipt['child_creation'] = 'NOT_STARTED'
    elif receipt['child_seen']:
        receipt['child_creation'] = 'OWNED'
    if 'TERM_REQUESTED' in messages.events and not receipt['actor_term_requested']:
        receipt['actor_term_requested'] = True
        fail(receipt, 'HARD_MOCK_ACTOR_TERM', receipt['phase']
             if receipt['first_failure'] else 'MOCK_FAILED')
    if 'CHILD_UNCONFIRMED' in messages.events:
        receipt['child_creation'] = 'OWNERSHIP_UNCONFIRMED'
        for code in messages.child_cleanup_errors:
            if code not in receipt['cleanup_errors']:
                receipt['cleanup_errors'].append(code)
        fail(receipt, messages.child_failure, 'CLEANUP_UNCERTAIN')
        receipt['termination'] = 'NOT_CONFIRMED'
    elif receipt['child_reaped'] and receipt['child_exit_code'] != 0 \
            and not receipt['actor_term_requested'] and not receipt['deadline_observed']:
        fail(receipt, 'HARD_MOCK_CHILD_EXIT')


def _cleanup(process, receipt, fd, messages):
    started = time.monotonic()
    errors = receipt['cleanup_errors']
    for label, signum, end in (('TERM', signal.SIGTERM, started + TERM_SECONDS),
                              ('KILL', signal.SIGKILL, started + TERM_SECONDS + KILL_SECONDS)):
        try:
            if _exited(process):
                break
            _owned(process)
            os.killpg(process.pid, signum)
            receipt['signals'].append(label)
            while time.monotonic() < end:
                try:
                    _drain(fd, messages)
                except Refused:
                    fail(receipt, 'HARD_MOCK_PROTOCOL')
                if _exited(process):
                    break
                time.sleep(.002)
        except (OSError, ChildProcessError, Refused) as error:
            # Exiting between the no-reap check and signal is not proof of a
            # leaked process. Stop signaling, then independently wait and verify
            # the group below. Other identity/signal failures stay uncertain.
            if isinstance(error, (ProcessLookupError, Refused)):
                try:
                    if _exited(process):
                        break
                except (OSError, ChildProcessError):
                    pass
            errors.append('HARD_MOCK_SIGNAL_OR_IDENTITY')
            break  # Never signal an unverified group or broaden cleanup.
    try:
        process.wait(timeout=max(.001, started + TERM_SECONDS + KILL_SECONDS - time.monotonic()))
        receipt['actor_exit_code'] = process.returncode
        require(_group_gone(process.pid), 'HARD_MOCK_GROUP_REMAINS')
        _drain(fd, messages)
        _claims(receipt, messages)
        if receipt['child_seen']:
            require('CHILD_REAPED' in messages.events, 'HARD_MOCK_CHILD_UNCONFIRMED')
    except (OSError, ChildProcessError, subprocess.TimeoutExpired, Refused):
        errors.append('HARD_MOCK_REAP_OR_GROUP')
    receipt['cleanup_elapsed_seconds'] = max(0., time.monotonic() - started)
    _claims(receipt, messages)
    receipt['termination'] = 'NOT_CONFIRMED' if errors else 'TERMINATION_CONFIRMED'
    if errors:
        fail(receipt, 'HARD_MOCK_CLEANUP', 'CLEANUP_UNCERTAIN')


def _drive(process, fd, spec, receipt, started, *, clock=time.monotonic):
    messages = Messages(spec, process.pid)
    previous = started
    deadline = started + spec['timeout_ms'] / 1000
    try:
        _bound(process)
        receipt['ownership_checked'] = True
        while True:
            now = clock()
            require(math.isfinite(now) and now >= previous, 'HARD_MOCK_CLOCK')
            previous = now
            if now >= deadline:
                receipt['deadline_observed'] = True
                fail(receipt, 'HARD_MOCK_DEADLINE', 'MOCK_TIMED_OUT')
                break
            _drain(fd, messages)
            _claims(receipt, messages)
            if receipt['actor_term_requested'] or receipt['child_creation'] == \
                    'OWNERSHIP_UNCONFIRMED':
                break
            if messages.child_pid is not None and not receipt['child_reaped']:
                require(os.getpgid(messages.child_pid) == process.pid, 'HARD_MOCK_OWNERSHIP')
            if spec['scenario'] == 'block_fifo_open' and 'READY' in messages.events:
                # Exact owned PID only, no process scan; this control read is NOT_PROVEN hard I/O.
                try:
                    state = Path('/proc', str(process.pid), 'wchan').read_text().strip()
                    receipt['fifo_block_observed'] |= state == 'wait_for_partner'
                except OSError:
                    pass  # Evidence remains false; the Linux test must refuse an unproved claim.
            if _exited(process):
                _drain(fd, messages)
                break
            select.select([fd], [], [], min(.01, deadline - now))
    except (OSError, ChildProcessError, Refused) as error:
        fail(receipt, str(error) if isinstance(error, Refused) else 'HARD_MOCK_OS')
    finally:
        finished = clock()
        if not math.isfinite(finished) or finished < previous:
            fail(receipt, 'HARD_MOCK_CLOCK')
        else:
            receipt['root_elapsed_seconds'] = max(0., finished - started)
            if finished >= deadline and receipt['first_failure'] is None:
                receipt['deadline_observed'] = True
                fail(receipt, 'HARD_MOCK_DEADLINE', 'MOCK_TIMED_OUT')
        _cleanup(process, receipt, fd, messages)
    if receipt['phase'] != 'CLEANUP_UNCERTAIN':
        if receipt['actor_exit_code'] != 0:
            fail(receipt, 'HARD_MOCK_EXIT', 'MOCK_TIMED_OUT' if receipt['deadline_observed']
                 else 'MOCK_FAILED')
        elif not messages.finished():
            fail(receipt, 'HARD_MOCK_MISSING_RECEIPT', 'MOCK_TIMED_OUT'
                 if receipt['deadline_observed'] else 'MOCK_FAILED')
        if receipt['first_failure'] is None:
            receipt['phase'] = 'MOCK_COMPLETE'
    return receipt


def run(spec):
    validate_request(spec)
    receipt = empty_receipt(spec)
    if sys.platform != 'linux' or not all(hasattr(os, x) for x in ('waitid', 'WNOWAIT', 'getpgid')):
        fail(receipt, 'HARD_MOCK_UNSUPPORTED', 'WATCHDOG_UNAVAILABLE')
        return receipt
    reserve(spec)
    started = time.monotonic()
    read_fd = write_fd = directory_fd = None
    try:
        with tempfile.TemporaryDirectory(prefix='perf03_hard_mock_') as parent:
            directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            read_fd, write_fd = os.pipe()
            os.set_blocking(read_fd, False)
            command = [sys.executable, '-I', '-S', str(ROOT/'perf03_lnx_hard_mock_actor.py'),
                       '--mock', '--run-id', spec['run_id'], '--scenario', spec['scenario'],
                       '--timeout-ms', str(spec['timeout_ms']), '--pipe-fd', str(write_fd),
                       '--directory-fd', str(directory_fd)]
            try:
                process = subprocess.Popen(command, shell=False, start_new_session=True,
                    pass_fds=(write_fd, directory_fd), env=ENV.copy(), stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                fail(receipt, 'HARD_MOCK_SPAWN', 'WATCHDOG_UNAVAILABLE')
            else:
                receipt['actor_pid'] = receipt['actor_pgid'] = process.pid
                os.close(write_fd)
                write_fd = None
                _drive(process, read_fd, spec, receipt, started)
    except (OSError, Refused):
        if receipt['actor_pid'] is None:
            fail(receipt, 'HARD_MOCK_CONTROL_IO', 'WATCHDOG_UNAVAILABLE')
        else:
            receipt['cleanup_errors'].append('HARD_MOCK_CONTROL_IO')
            receipt['termination'] = 'NOT_CONFIRMED'
            fail(receipt, 'HARD_MOCK_CLEANUP', 'CLEANUP_UNCERTAIN')
    finally:
        for fd in (read_fd, write_fd, directory_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    receipt['cleanup_errors'].append('HARD_MOCK_CLOSE')
                    receipt['termination'] = 'NOT_CONFIRMED'
                    fail(receipt, 'HARD_MOCK_CLEANUP', 'CLEANUP_UNCERTAIN')
    validate_receipt(receipt, spec)
    return receipt


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'HARD_MOCK_ARGUMENTS\n')


def main(argv=None):
    parser = _Parser(prog='perf03-hard-mock', description=__doc__)
    parser.add_argument('--mock', action='store_true', required=True)
    parser.add_argument('--scenario', choices=SCENARIOS, required=True)
    parser.add_argument('--timeout-ms', type=int, default=500)
    args = parser.parse_args(argv)
    try:
        spec = request(args.scenario, timeout_ms=args.timeout_ms)
        receipt = run(spec)
    except Refused:
        print('HARD_MOCK_REFUSED')
        return 2
    print(canonical(receipt).decode('ascii'))
    return 0 if receipt['phase'] == 'MOCK_COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
