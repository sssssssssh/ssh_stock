"""Pure Mock contracts; no application, database or Linux resource requirement."""

import copy

import pytest

from scripts import perf03_lnx_hard_watchdog as w


def test_request_and_receipt_cannot_authorize_real_execution():
    request = w.request('success', run_id='SYNTHETIC_' + 'A' * 32)
    result = w.empty_receipt(request)
    w.fail(result, 'HARD_MOCK_UNSUPPORTED', 'WATCHDOG_UNAVAILABLE')
    w.validate_receipt(result, request)
    assert result['REAL_MEASUREMENT'] is False
    assert result['AC05_STATUS'] == result['R1_STATUS'] == 'PARTIAL'
    assert not any(result['authorization'].values())
    changed = copy.deepcopy(result)
    changed['authorization']['real_execution'] = True
    with pytest.raises(w.Refused):
        w.validate_receipt(changed, request)


@pytest.mark.parametrize('mutate', [
    lambda s: s.update(command='echo PRIVATE'), lambda s: s.update(pid=123),
    lambda s: s.update(pgid=123), lambda s: s.update(path='/PRIVATE'),
    lambda s: s.update(module='app.jobs'), lambda s: s.update(url='https://PRIVATE'),
    lambda s: s.update(scenario='--real'), lambda s: s.update(scenario='pg'),
    lambda s: s.update(scenario='worker'), lambda s: s.update(scenario=[]),
    lambda s: s.update(timeout_ms=True), lambda s: s.update(timeout_ms=99),
    lambda s: s.update(timeout_ms=1001), lambda s: s.update(run_id='41991816127'),
    lambda s: s.update(run_id='SYNTHETIC_OLD'), lambda s: s.update(schema='real'),
])
def test_unapproved_request_refused_before_io(monkeypatch, mutate):
    spec = w.request()
    mutate(spec)
    monkeypatch.setattr(w.tempfile, 'TemporaryDirectory', lambda **kw: pytest.fail('I/O'))
    monkeypatch.setattr(w.subprocess, 'Popen', lambda *a, **kw: pytest.fail('spawn'))
    with pytest.raises(w.Refused):
        w.run(spec)


@pytest.mark.parametrize('args', [[], ['--real'], ['--pg'], ['--worker'],
    ['--mock', '--scenario', 'success', '--command', 'PRIVATE'],
    ['--mock', '--scenario', 'success', '--pid', '123'],
    ['--mock', '--scenario', 'success', '--pgid', '123']])
def test_cli_refuses_free_execution_before_io(monkeypatch, args):
    monkeypatch.setattr(w.tempfile, 'TemporaryDirectory', lambda **kw: pytest.fail('I/O'))
    with pytest.raises(SystemExit) as caught:
        w.main(args)
    assert caught.value.code == 2


@pytest.mark.parametrize('platform', ['darwin', 'win32'])
def test_non_linux_is_explicit_unsupported_without_spawn(monkeypatch, platform):
    monkeypatch.setattr(w.sys, 'platform', platform)
    monkeypatch.setattr(w.subprocess, 'Popen', lambda *a, **kw: pytest.fail('spawn'))
    monkeypatch.setattr(w.os, 'killpg', lambda *a: pytest.fail('signal'))
    spec = w.request()
    r = w.run(spec)
    assert r['phase'] == 'WATCHDOG_UNAVAILABLE'
    assert r['first_failure'] == 'HARD_MOCK_UNSUPPORTED'
    assert r['termination'] == 'NOT_STARTED'
    w.validate_receipt(r, spec)


def test_same_run_reservation_is_single_use(monkeypatch):
    monkeypatch.setattr(w, '_USED', set())
    spec = w.request()
    w.reserve(spec)
    with pytest.raises(w.Refused, match='HARD_MOCK_REPLAY'):
        w.reserve(spec)
    assert len(w._USED) == 1


def message(spec, event='READY', pid=123, child_pid=None):
    return dict(v=1, run_id=spec['run_id'], spec_sha256=w.spec_hash(spec), pid=pid,
                pgid=pid, event=event, child_pid=child_pid)


@pytest.mark.parametrize('mutate', [
    lambda m: m.update(pid=124), lambda m: m.update(pgid=0), lambda m: m.update(pid=True),
    lambda m: m.update(run_id='SYNTHETIC_' + 'F' * 32),
    lambda m: m.update(spec_sha256='0' * 64), lambda m: m.update(event='DONE'),
    lambda m: m.update(event='PERFORMANCE_PASS'), lambda m: m.update(v=True),
    lambda m: m.update(path='/PRIVATE'), lambda m: m.update(child_pid=0),
])
def test_protocol_rejects_other_identity_order_and_free_fields(mutate):
    spec = w.request()
    m = message(spec)
    mutate(m)
    with pytest.raises(w.Refused):
        w.Messages(spec, 123).feed(w.canonical(m) + b'\n')


@pytest.mark.parametrize('raw', [b'{\n', b'\xff\n', b'{"a":1,"a":2}\n', b'x' * 4097,
                                b'[' * 1500 + b']' * 1500 + b'\n'],
                         ids=['malformed', 'encoding', 'duplicate', 'oversize', 'depth'])
def test_protocol_malformed_or_oversized_is_not_success(raw):
    with pytest.raises(w.Refused):
        w.Messages(w.request(), 123).feed(raw)


def test_protocol_stream_chunking_replay_and_missing_receipt():
    spec = w.request()
    stream = w.Messages(spec, 123)
    raw = w.canonical(message(spec)) + b'\n'
    stream.feed(raw[:10])
    assert not stream.finished()
    stream.feed(raw[10:])
    stream.feed(w.canonical(message(spec, 'DONE')) + b'\n')
    assert stream.finished()
    with pytest.raises(w.Refused):
        stream.feed(raw)
    other = w.request()
    with pytest.raises(w.Refused):
        w.Messages(other, 123).feed(raw)


@pytest.mark.parametrize('fault', ['signal', 'wait', 'group', 'identity', 'orphan'])
def test_cleanup_failures_are_uncertain_and_never_signal_unknown_group(monkeypatch, fault):
    class Process:
        pid = 123
        returncode = None
        exited = fault == 'orphan'

        def wait(self, timeout):
            assert 0 < timeout <= .401
            if fault in {'wait', 'signal', 'identity'}:
                raise w.subprocess.TimeoutExpired('FIXED_MOCK', timeout)
            self.returncode = -15

    proc = Process()
    spec = w.request()
    receipt = w.empty_receipt(spec)
    receipt.update(actor_pid=123, actor_pgid=123)
    w.fail(receipt, 'HARD_MOCK_DEADLINE', 'MOCK_TIMED_OUT')
    receipt['deadline_observed'] = True
    verified, signals = [], []

    def owned(p):
        verified.append(p.pid)
        if fault == 'identity':
            raise w.Refused('HARD_MOCK_OWNERSHIP')

    def signal_group(pid, signum):
        assert pid == 123 and verified
        signals.append((pid, signum))
        if fault == 'signal':
            raise OSError('PRIVATE')
        proc.exited = True

    monkeypatch.setattr(w, '_owned', owned)
    monkeypatch.setattr(w, '_exited', lambda p: p.exited)
    monkeypatch.setattr(w.os, 'killpg', signal_group)
    monkeypatch.setattr(w, '_group_gone', lambda pid: fault not in {'group', 'orphan'})
    monkeypatch.setattr(w, '_drain', lambda *a: None)
    w._cleanup(proc, receipt, 0, w.Messages(spec, 123))
    assert receipt['phase'] == 'CLEANUP_UNCERTAIN'
    assert receipt['first_failure'] == 'HARD_MOCK_DEADLINE'
    assert receipt['termination'] == 'NOT_CONFIRMED'
    assert receipt['cleanup_errors']
    assert 'PRIVATE' not in w.canonical(receipt).decode()
    if fault in {'identity', 'orphan'}:
        assert signals == []
    w.validate_receipt(receipt, spec)


@pytest.mark.parametrize('now,expected', [(1.5, 'HARD_MOCK_DEADLINE'),
    (.9, 'HARD_MOCK_CLOCK'), (float('nan'), 'HARD_MOCK_CLOCK'),
    (float('inf'), 'HARD_MOCK_CLOCK')])
def test_equal_deadline_clock_anomalies_and_late_done_fail_closed(monkeypatch, now, expected):
    class Process:
        pid = 123

    spec = w.request(timeout_ms=500)
    receipt = w.empty_receipt(spec)
    receipt.update(actor_pid=123, actor_pgid=123)
    monkeypatch.setattr(w, '_bound', lambda p: None)

    def finish(p, r, fd, messages):
        # A late actor success cannot erase an already established deadline/error.
        messages.feed(w.canonical(message(spec)) + b'\n')
        messages.feed(w.canonical(message(spec, 'DONE')) + b'\n')
        r.update(actor_exit_code=0, termination='TERMINATION_CONFIRMED')

    monkeypatch.setattr(w, '_cleanup', finish)
    r = w._drive(Process(), 0, spec, receipt, 1., clock=lambda: now)
    assert r['first_failure'] == expected
    assert r['phase'] != 'MOCK_COMPLETE'
    w.validate_receipt(r, spec)


@pytest.mark.parametrize('field,value', [('phase', 'MOCK_COMPLETE'), ('R1_STATUS', 'PASS'),
    ('AC05_STATUS', 'CLOSED'), ('REAL_MEASUREMENT', True),
    ('PERFORMANCE_ELIGIBILITY', 'PASS'), ('spec_sha256', '0' * 64),
    ('run_id', 'SYNTHETIC_' + 'F' * 32), ('actor_pid', 0), ('signals', ['KILL'])])
def test_receipt_cannot_upgrade_or_mix_evidence(field, value):
    spec = w.request()
    r = w.empty_receipt(spec)
    w.fail(r, 'HARD_MOCK_UNSUPPORTED', 'WATCHDOG_UNAVAILABLE')
    r[field] = value
    with pytest.raises(w.Refused):
        w.validate_receipt(r, spec)


def test_spawn_is_fixed_minimal_and_failure_does_not_retry(monkeypatch):
    monkeypatch.setattr(w.sys, 'platform', 'linux')
    monkeypatch.setattr(w.os, 'waitid', lambda *a: None, raising=False)
    monkeypatch.setattr(w.os, 'WNOWAIT', 0, raising=False)
    calls = []

    def spawn(command, **kw):
        calls.append(command)
        assert command[:3] == [w.sys.executable, '-I', '-S']
        assert command[3] == str(w.ROOT/'perf03_lnx_hard_mock_actor.py')
        assert '--command' not in command and '--pid' not in command
        assert kw['shell'] is False and kw['start_new_session'] is True
        assert kw['env'] == w.ENV and set(kw['env']) == {
            'PYTHONDONTWRITEBYTECODE', 'PYTHONUNBUFFERED'}
        assert len(kw['pass_fds']) == 2
        assert kw['stdin'] == kw['stdout'] == kw['stderr'] == w.subprocess.DEVNULL
        raise OSError('PRIVATE')

    monkeypatch.setattr(w.subprocess, 'Popen', spawn)
    spec = w.request()
    r = w.run(spec)
    assert len(calls) == 1 and r['first_failure'] == 'HARD_MOCK_SPAWN'
    assert r['phase'] == 'WATCHDOG_UNAVAILABLE'
    assert 'PRIVATE' not in w.canonical(r).decode()


def test_static_and_fresh_import_guard_are_standard_library_only():
    import ast
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    allowed = {'argparse', 'hashlib', 'json', 'math', 'os', 're', 'select', 'signal',
               'subprocess', 'sys', 'tempfile', 'time', 'uuid', 'pathlib',
               'perf03_lnx_hard_watchdog'}
    for name in ('watchdog', 'mock_actor'):
        tree = ast.parse((root/f'scripts/perf03_lnx_hard_{name}.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name in allowed for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert node.module in allowed
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {'eval', 'exec', '__import__'}
    program = '''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import subprocess
subprocess.Popen = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('NO_WORKLOAD'))
import perf03_lnx_hard_watchdog
import perf03_lnx_hard_mock_actor
forbidden = ('app', 'backend', 'sqlalchemy', 'psycopg', 'tushare', 'socket',
             'scripts.performance_diagnostics_overhead', 'scripts.v14_test_database')
if any(n == p or n.startswith(p + '.') for n in sys.modules for p in forbidden):
    raise SystemExit(31)
print('HARD_MOCK_IMPORT_OK')
'''
    result = subprocess.run([sys.executable, '-I', '-S', '-c', program, str(root/'scripts')],
        shell=False, env={}, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert result.stdout == 'HARD_MOCK_IMPORT_OK\n' and result.stderr == ''


@pytest.mark.parametrize('fault', ['pid', 'reaped', 'pgid', 'sid', 'exited'])
def test_pid_reuse_or_wrong_group_never_reaches_signal(monkeypatch, fault):
    class Process:
        pid = 1 if fault == 'pid' else 123
        returncode = 0 if fault == 'reaped' else None

    monkeypatch.setattr(w.os, 'getpgid', lambda pid: 124 if fault == 'pgid' else 123)
    monkeypatch.setattr(w.os, 'getsid', lambda pid: 124 if fault == 'sid' else 123)
    monkeypatch.setattr(w, '_exited', lambda p: fault == 'exited')
    monkeypatch.setattr(w.os, 'killpg', lambda *a: pytest.fail('unverified signal'))
    with pytest.raises(w.Refused):
        w._owned(Process())


def test_actor_cannot_skip_child_reaping_protocol():
    spec = w.request('child_same_group')
    stream = w.Messages(spec, 123)
    stream.feed(w.canonical(message(spec)) + b'\n')
    stream.feed(w.canonical(message(spec, 'CHILD', child_pid=124)) + b'\n')
    with pytest.raises(w.Refused):
        stream.feed(w.canonical(message(spec, 'DONE', child_pid=124)) + b'\n')
    assert not stream.finished()


def test_cli_errors_never_echo_free_private_input(capsys):
    with pytest.raises(SystemExit):
        w.main(['--mock', '--scenario', 'success', '--dsn', 'postgresql://PRIVATE'])
    assert capsys.readouterr().err == 'HARD_MOCK_ARGUMENTS\n'


@pytest.mark.parametrize('point', ['identity_check', 'signal_esrch'])
def test_owned_actor_exit_during_cleanup_is_reaped_without_false_uncertainty(monkeypatch, point):
    class Process:
        pid = 123
        returncode = None
        exited = False

        def wait(self, timeout):
            self.returncode = 0

    proc = Process()
    spec = w.request()
    receipt = w.empty_receipt(spec)
    receipt.update(actor_pid=123, actor_pgid=123, ownership_checked=True)
    w.fail(receipt, 'HARD_MOCK_PROTOCOL')

    def owned(p):
        if point == 'identity_check':
            proc.exited = True
            raise w.Refused('HARD_MOCK_OWNERSHIP')

    def signal_group(pid, signum):
        assert pid == 123
        proc.exited = True
        raise ProcessLookupError('already exited')

    monkeypatch.setattr(w, '_exited', lambda p: p.exited)
    monkeypatch.setattr(w, '_owned', owned)
    monkeypatch.setattr(w.os, 'killpg', signal_group)
    monkeypatch.setattr(w, '_group_gone', lambda pid: True)
    monkeypatch.setattr(w, '_drain', lambda *a: None)
    w._cleanup(proc, receipt, 0, w.Messages(spec, 123))
    assert receipt['phase'] == 'MOCK_FAILED'
    assert receipt['first_failure'] == 'HARD_MOCK_PROTOCOL'
    assert receipt['termination'] == 'TERMINATION_CONFIRMED'
    assert receipt['cleanup_errors'] == [] and receipt['signals'] == []
    w.validate_receipt(receipt, spec)


def test_json_parser_recursion_failure_is_sanitized_and_refused(monkeypatch):
    def exhausted(*args, **kwargs):
        raise RecursionError('PRIVATE')

    monkeypatch.setattr(w.json, 'loads', exhausted)
    with pytest.raises(w.Refused, match='^HARD_MOCK_PROTOCOL$'):
        w.Messages(w.request(), 123).feed(b'{}\n')


def test_term_before_same_group_child_spawn_never_leaves_child_unreaped():
    """No real Linux/child: deterministic TERM-before-Popen-return resource race."""
    import subprocess
    import sys

    program = '''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import perf03_lnx_hard_mock_actor as actor
handlers = {}
class Child:
    pid = 124
    terminated = False
    def terminate(self):
        self.terminated = True
    def wait(self, timeout):
        if not self.terminated:
            raise actor.subprocess.TimeoutExpired('FIXED_MOCK_CHILD', timeout)
        return -15
child = Child()
def spawn(*args, **kwargs):
    handlers[actor.signal.SIGTERM](actor.signal.SIGTERM, None)
    return child
actor.sys.platform = 'linux'
actor.os.getpid = lambda: 123
actor.os.getpgrp = lambda: 123
actor.os.getsid = lambda pid: 123
actor.os.write = lambda fd, raw: len(raw)
actor.signal.signal = lambda sig, handler: handlers.update({sig: handler})
actor.subprocess.Popen = spawn
try:
    code = actor.main(['--mock', '--run-id', 'SYNTHETIC_' + 'A' * 32,
        '--scenario', 'child_same_group', '--timeout-ms', '500',
        '--pipe-fd', '10', '--directory-fd', '11'])
except actor.subprocess.TimeoutExpired:
    print('HARD_MOCK_CHILD_UNREAPED')
    raise SystemExit(3)
if code != 0 or not child.terminated:
    raise SystemExit(4)
print('HARD_MOCK_CHILD_REAPED')
'''
    result = subprocess.run([sys.executable, '-I', '-S', '-c', program, str(w.ROOT)],
        shell=False, env={}, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3)
    assert result.returncode == 0
    assert result.stdout == 'HARD_MOCK_CHILD_REAPED\n' and result.stderr == ''


@pytest.fixture
def race_actor(monkeypatch):
    import importlib.util
    import sys

    original_path = sys.path[:]
    monkeypatch.setitem(sys.modules, 'perf03_lnx_hard_watchdog', w)
    spec = importlib.util.spec_from_file_location('race_actor_under_test',
                                                w.ROOT/'perf03_lnx_hard_mock_actor.py')
    actor = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(actor)
    finally:
        sys.path[:] = original_path
    # Pure injected SID/PID, no real process lookup or signaling in this fixture.
    monkeypatch.setattr(actor.os, 'getpgrp', lambda: 123)
    monkeypatch.setattr(actor.os, 'getsid', lambda pid: 123)
    return actor


class RaceChild:
    pid = 124
    returncode = None

    def __init__(self, mode='normal', on_term=lambda: None):
        self.mode = mode
        self.on_term = on_term
        self.alive = mode != 'fast'
        self.actions = []
        self.reaps = 0
        self.wait_limits = []

    def wait(self, timeout):
        self.wait_limits.append(timeout)
        assert 0 <= timeout <= .1
        if self.mode == 'wait_error':
            raise OSError('PRIVATE')
        if self.alive:
            raise w.subprocess.TimeoutExpired('FIXED_MOCK_CHILD', timeout)
        self.reaps += 1
        self.returncode = -9 if 'KILL' in self.actions else -15 if self.actions else 0
        return self.returncode

    def terminate(self):
        self.actions.append('TERM')
        self.on_term()
        if self.mode == 'term_error':
            raise OSError('PRIVATE')
        if self.mode not in {'ignore', 'kill_error', 'unreapable'}:
            self.alive = False

    def kill(self):
        self.actions.append('KILL')
        if self.mode == 'kill_error':
            raise OSError('PRIVATE')
        if self.mode != 'unreapable':
            self.alive = False


def race_create(actor, monkeypatch, child, stopped, *, before_return=lambda: None):
    from types import SimpleNamespace

    calls = []

    def spawn(command, **kwargs):
        calls.append(command)
        assert command[:3] == [actor.sys.executable, '-I', '-S']
        assert command[3] == str(w.ROOT/'perf03_lnx_hard_mock_actor.py')
        assert kwargs['shell'] is False and kwargs['start_new_session'] is False
        assert kwargs['process_group'] == actor.os.getpgrp() == 123
        assert kwargs['env'] == w.ENV
        before_return()
        return child

    monkeypatch.setattr(actor.subprocess, 'Popen', spawn)
    owner = actor.ChildLifecycle()
    owner.create(SimpleNamespace(pipe_fd=10, directory_fd=11),
                 w.request('child_same_group'), stopped)
    return owner, calls


@pytest.mark.parametrize('point', ['before', 'during', 'after'])
def test_race01_term_boundaries_use_owned_handle_once(race_actor, monkeypatch, point):
    stopped = [point == 'before']
    child = RaceChild()

    def during():
        if point == 'during':
            stopped[0] = True

    owner, calls = race_create(race_actor, monkeypatch, child, stopped, before_return=during)
    if point == 'after':
        stopped[0] = True
    result = owner.cleanup()
    assert stopped[0]
    assert result['state'] == ('NOT_STARTED' if point == 'before' else 'REAPED')
    assert len(calls) == (0 if point == 'before' else 1)
    assert child.actions == ([] if point == 'before' else ['TERM'])
    assert child.reaps == (0 if point == 'before' else 1)
    assert owner.cleanup() == result
    assert child.reaps == (0 if point == 'before' else 1)
    with pytest.raises(w.Refused):
        owner.create(None, w.request('child_same_group'), stopped)


@pytest.mark.parametrize('mode', ['fast', 'ignore', 'normal'])
def test_race01_fast_exit_kill_escalation_and_repeat_term_are_idempotent(
        race_actor, monkeypatch, mode):
    stopped = [False]
    requests = []

    def repeated_term():
        for _ in range(2):
            stopped[0] = True
            requests.append('TERM_INTENT')  # No recursive cleanup from the handler.

    child = RaceChild(mode, on_term=repeated_term)
    owner, calls = race_create(race_actor, monkeypatch, child, stopped)
    result = owner.cleanup()
    assert result['state'] == 'REAPED' and result['cleanup_errors'] == ()
    assert len(calls) == 1 and child.reaps == 1
    assert child.actions == ([] if mode == 'fast' else ['TERM', 'KILL']
                             if mode == 'ignore' else ['TERM'])
    assert requests == ([] if mode == 'fast' else ['TERM_INTENT', 'TERM_INTENT'])
    assert result['child_exit_code'] == (0 if mode == 'fast' else -9 if mode == 'ignore' else -15)
    assert owner.cleanup() == result and child.reaps == 1


@pytest.mark.parametrize('failure', ['oserror', 'interrupted', 'no_handle'])
def test_race01_failed_spawn_is_unknown_not_claimed_not_started(race_actor, monkeypatch, failure):
    from types import SimpleNamespace

    def spawn(*args, **kwargs):
        if failure == 'oserror':
            raise OSError('PRIVATE')
        if failure == 'interrupted':
            raise KeyboardInterrupt
        return None

    monkeypatch.setattr(race_actor.subprocess, 'Popen', spawn)
    owner = race_actor.ChildLifecycle()
    owner.create(SimpleNamespace(pipe_fd=10, directory_fd=11),
                 w.request('child_same_group'), [False])
    result = owner.cleanup()
    assert result['state'] == 'OWNERSHIP_UNCONFIRMED'
    assert result['first_failure'] == 'HARD_MOCK_CHILD_START_UNKNOWN'
    assert result['child_exit_code'] is None and result['actions'] == ()
    assert 'PRIVATE' not in str(result)


@pytest.mark.parametrize('mode', ['term_error', 'wait_error', 'kill_error', 'unreapable'])
def test_race01_wait_and_signal_failures_cannot_claim_reaped(race_actor, monkeypatch, mode):
    child = RaceChild(mode)
    owner, _ = race_create(race_actor, monkeypatch, child, [False])
    result = owner.cleanup()
    assert result['state'] == 'OWNERSHIP_UNCONFIRMED'
    assert result['first_failure'] == 'HARD_MOCK_CHILD_CLEANUP'
    assert result['cleanup_errors'] == ('HARD_MOCK_CHILD_CLEANUP',)
    assert 'PRIVATE' not in str(result)
    assert owner.cleanup() == result


@pytest.mark.parametrize('mismatch', ['pid', 'sid', 'reaped_handle'])
def test_race01_wrong_child_identity_never_receives_signal(race_actor, monkeypatch, mismatch):
    child = RaceChild()
    if mismatch == 'pid':
        child.pid = 1
    elif mismatch == 'reaped_handle':
        child.returncode = 0  # Contradicts the injected wait timeout: cannot trust ownership.
    else:
        monkeypatch.setattr(race_actor.os, 'getsid', lambda pid: 999)
    owner, _ = race_create(race_actor, monkeypatch, child, [False])
    result = owner.cleanup()
    assert result['state'] == 'OWNERSHIP_UNCONFIRMED'
    assert result['first_failure'] == 'HARD_MOCK_CHILD_IDENTITY'
    assert child.actions == []


def test_race01_cleanup_budget_is_not_restarted(race_actor, monkeypatch):
    child = RaceChild('ignore')
    owner, _ = race_create(race_actor, monkeypatch, child, [False])
    samples = iter((10., 10.01, 10.11))
    monkeypatch.setattr(race_actor.time, 'monotonic', lambda: next(samples))
    result = owner.cleanup()
    assert result['state'] == 'OWNERSHIP_UNCONFIRMED'
    assert result['first_failure'] == 'HARD_MOCK_CHILD_BUDGET'
    assert child.actions == ['TERM']
    assert owner.cleanup() == result  # Does not sample clock again or grant a new budget.


def test_race01_unknown_child_cannot_be_upgraded_by_actor_done():
    spec = w.request('child_same_group')
    messages = w.Messages(spec, 123)
    messages.feed(w.canonical(message(spec)) + b'\n')
    bad = message(spec, 'CHILD_UNCONFIRMED')
    bad.update(child_failure='HARD_MOCK_CHILD_START_UNKNOWN',
               cleanup_errors=['HARD_MOCK_CHILD_START_UNKNOWN'])
    messages.feed(w.canonical(bad) + b'\n')
    r = w.empty_receipt(spec)
    w._claims(r, messages)
    assert r['phase'] == 'CLEANUP_UNCERTAIN'
    assert r['child_creation'] == 'OWNERSHIP_UNCONFIRMED'
    w.validate_receipt(r, spec)
    with pytest.raises(w.Refused):
        messages.feed(w.canonical(message(spec, 'DONE')) + b'\n')


def test_race01_no_child_after_term_is_not_mock_work_success():
    spec = w.request('child_same_group')
    messages = w.Messages(spec, 123)
    for event in ('READY', 'TERM_REQUESTED', 'CHILD_NOT_STARTED', 'DONE'):
        messages.feed(w.canonical(message(spec, event)) + b'\n')
    r = w.empty_receipt(spec)
    w._claims(r, messages)
    assert messages.finished()
    assert r['actor_term_requested'] and r['child_creation'] == 'NOT_STARTED'
    assert r['phase'] == 'MOCK_FAILED' and r['first_failure'] == 'HARD_MOCK_ACTOR_TERM'
    w.validate_receipt(r, spec)


def test_race01_child_cleanup_error_preserves_prior_deadline():
    spec = w.request('child_same_group')
    messages = w.Messages(spec, 123)
    for event in ('READY', 'CHILD', 'TERM_REQUESTED'):
        messages.feed(w.canonical(message(spec, event,
            child_pid=None if event == 'READY' else 124)) + b'\n')
    bad = message(spec, 'CHILD_UNCONFIRMED', child_pid=124)
    bad.update(child_failure='HARD_MOCK_CHILD_CLEANUP',
               cleanup_errors=['HARD_MOCK_CHILD_CLEANUP'])
    messages.feed(w.canonical(bad) + b'\n')
    r = w.empty_receipt(spec)
    r['deadline_observed'] = True
    w.fail(r, 'HARD_MOCK_DEADLINE', 'MOCK_TIMED_OUT')
    w._claims(r, messages)
    assert r['phase'] == 'CLEANUP_UNCERTAIN' and r['first_failure'] == 'HARD_MOCK_DEADLINE'
    assert r['failure_reason'] == ['HARD_MOCK_DEADLINE', 'HARD_MOCK_ACTOR_TERM',
                                  'HARD_MOCK_CHILD_CLEANUP']
    w.validate_receipt(r, spec)


def fix02_injected_drive(monkeypatch, *, fragmented=False, stubborn=False,
                        unknown_child=False, exit_code=0):
    """A cooperative actor is still alive after sending TERM; never a real PID."""
    class Process:
        pid = 123
        returncode = None
        exited = False
        code = exit_code

        def wait(self, timeout):
            if not self.exited:
                raise w.subprocess.TimeoutExpired('FIXED_MOCK', timeout)
            self.returncode = self.code
            return self.code

    process = Process()
    spec = w.request('child_term_before_spawn', timeout_ms=500)
    result = w.empty_receipt(spec)
    result.update(actor_pid=123, actor_pgid=123)
    stream, progress, signals, ticks = [], [0], [], [0]

    def drain(fd, messages):
        if process.code == -15:  # A redundant group TERM interrupts orderly interpreter exit.
            return
        if not stream:
            events = ['READY'] if unknown_child else ['READY', 'TERM_REQUESTED']
            if not fragmented and not unknown_child:
                events += ['CHILD_NOT_STARTED', 'DONE']
            for event in events:
                messages.feed(w.canonical(message(spec, event)) + b'\n')
            stream.append('FIRST')
            if unknown_child:
                value = message(spec, 'CHILD_UNCONFIRMED')
                value.update(child_failure='HARD_MOCK_CHILD_START_UNKNOWN',
                             cleanup_errors=['HARD_MOCK_CHILD_START_UNKNOWN'])
                messages.feed(w.canonical(value) + b'\n')
        elif fragmented and progress[0] and len(stream) == 1:
            for event in ('CHILD_NOT_STARTED', 'DONE'):
                messages.feed(w.canonical(message(spec, event)) + b'\n')
            stream.append('FINAL')

    def poll(reads, writes, errors, timeout):
        assert 0 < timeout <= .01
        progress[0] += 1
        if not stubborn:
            process.exited = True  # Normal close after its already queued protocol bytes.
        return [], [], []

    def signal_group(pid, signum):
        assert pid == 123 and signum == w.signal.SIGTERM
        signals.append('TERM')
        process.code, process.exited = -15, True

    def clock():
        ticks[0] += 1
        return ticks[0] / 100

    monkeypatch.setattr(w, '_bound', lambda p: None)
    monkeypatch.setattr(w, '_owned', lambda p: None)
    monkeypatch.setattr(w, '_drain', drain)
    monkeypatch.setattr(w, '_exited', lambda p: p.exited)
    monkeypatch.setattr(w, '_group_gone', lambda pid: True)
    monkeypatch.setattr(w.os, 'killpg', signal_group)
    monkeypatch.setattr(w.select, 'select', poll)
    result = w._drive(process, 0, spec, result, 0., clock=clock)
    return result, spec, signals, progress[0]


@pytest.mark.parametrize('fragmented', [False, True])
def test_fix02_cooperative_term_does_not_interrupt_actor_exit(monkeypatch, fragmented):
    r, spec, signals, polls = fix02_injected_drive(monkeypatch, fragmented=fragmented)
    assert r['actor_exit_code'] == 0
    assert signals == [] and polls > 0
    assert r['phase'] == 'MOCK_FAILED' and r['first_failure'] == 'HARD_MOCK_ACTOR_TERM'
    assert r['actor_term_requested'] and r['child_creation'] == 'NOT_STARTED'
    assert not r['child_seen'] and not r['child_reaped']
    assert r['termination'] == 'TERMINATION_CONFIRMED' and not r['deadline_observed']
    w.validate_receipt(r, spec)


def test_fix02_cooperative_claim_cannot_extend_deadline_or_replace_first_failure(monkeypatch):
    r, spec, signals, polls = fix02_injected_drive(monkeypatch, stubborn=True)
    assert r['deadline_observed'] and r['root_elapsed_seconds'] >= .5
    assert signals == ['TERM'] and polls > 0
    assert r['phase'] == 'MOCK_FAILED' and r['first_failure'] == 'HARD_MOCK_ACTOR_TERM'
    assert 'HARD_MOCK_DEADLINE' in r['failure_reason']
    assert r['actor_exit_code'] == -15 and r['termination'] == 'TERMINATION_CONFIRMED'
    w.validate_receipt(r, spec)


def test_fix02_actual_nonzero_exit_is_never_rewritten_to_zero(monkeypatch):
    r, spec, signals, _ = fix02_injected_drive(monkeypatch, exit_code=7)
    assert r['actor_exit_code'] == 7 and signals == []
    assert r['phase'] == 'MOCK_FAILED' and r['first_failure'] == 'HARD_MOCK_ACTOR_TERM'
    assert 'HARD_MOCK_EXIT' in r['failure_reason']
    w.validate_receipt(r, spec)


def test_fix02_unknown_child_does_not_gain_cooperative_wait_or_success(monkeypatch):
    r, spec, signals, polls = fix02_injected_drive(monkeypatch, unknown_child=True)
    assert polls == 0 and signals == ['TERM']
    assert r['phase'] == 'CLEANUP_UNCERTAIN'
    assert r['first_failure'] == 'HARD_MOCK_CHILD_START_UNKNOWN'
    assert r['termination'] == 'NOT_CONFIRMED'
    w.validate_receipt(r, spec)
