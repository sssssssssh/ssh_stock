"""Only the registered standard-library mock child is ever launched."""

import copy
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import perf03_lnx_offline_contract as c
from scripts import perf03_lnx_offline_supervisor as s


def test_success_is_parent_verified_and_exclusively_archived(tmp_path):
    result = s.supervise(tmp_path.resolve(), 'SYNTHETIC_A')
    assert result['phase'] == 'COMPLETE_MOCK'
    c.validate_receipt(result, supervised=True)
    assert result['supervision']['child_reaped']
    assert result['supervision']['archive_verified']
    assert result['supervision']['process_cleanup'] == 'REAPED'
    with s.OwnedDirectory(tmp_path.resolve(), 'OTHER') as directory:
        directory.write('final.json', c.seal(result))
        assert c.unseal(directory.read('final.json')) == result
        with pytest.raises(FileExistsError):
            directory.write('final.json', c.seal(result))
    saved = c.unseal(c.load((tmp_path/'SYNTHETIC_A_OFF1/final.json').read_bytes()))
    assert saved == result


@pytest.mark.parametrize('scenario', sorted(s.SCENARIOS - {'success'}))
def test_all_failure_scenarios_fail_closed_and_reap_owned_child(tmp_path, scenario):
    children = []

    def spawn(*args, **kwargs):
        child = subprocess.Popen(*args, **kwargs)
        children.append(child)
        return child

    result = s.supervise(tmp_path.resolve(), 'SYNTHETIC_F', scenario=scenario,
                         limits=(.25, .25, .25), popen=spawn)
    assert result['phase'] != 'COMPLETE_MOCK'
    assert result['first_failure']
    assert result['supervision']['child_reaped']
    assert len(children) == 1 and children[0].poll() is not None
    assert not any(result['authorization'].values())
    prefix = c.unseal(c.load((tmp_path/'SYNTHETIC_F_OFF1/prefix.json').read_bytes()))
    assert prefix['phase'] == 'INCOMPLETE'
    assert not prefix['supervision']['child_reaped']


def test_prelaunch_deadline_starts_no_child(tmp_path):
    now = [0]

    def delayed():
        now[0] = 2

    result = s.supervise(tmp_path.resolve(), 'SYNTHETIC_LATE', clock=lambda: now[0],
        before_start=delayed, popen=lambda *a, **kw: pytest.fail('child must not start'))
    assert result['first_failure'] == 'MOCK_START_TIMEOUT'
    assert not result['supervision']['child_reaped']


def test_interrupt_preserves_first_error_and_only_kills_own_handle(tmp_path):
    class Interrupted:
        returncode = None
        killed = False

        def poll(self):
            if not self.killed:
                raise KeyboardInterrupt
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self, timeout):
            assert timeout <= .5
            return self.returncode

    # Interrupt once, then the same handle supports cleanup.
    child = Interrupted()
    first = [True]
    original = child.poll

    def poll():
        if first[0]:
            first[0] = False
            raise KeyboardInterrupt
        return child.returncode

    child.poll = poll
    result = s.supervise(tmp_path.resolve(), 'SYNTHETIC_INTERRUPT',
                         popen=lambda *a, **kw: child)
    assert result['first_failure'] == 'MOCK_PARENT_INTERRUPTED'
    assert child.killed
    assert original() == -9


def test_uncertain_kill_cannot_claim_cleanup_or_complete(tmp_path):
    class Unreaped:
        returncode = None

        def poll(self):
            return None

        def kill(self):
            raise OSError('private-path-and-password')

    now = [0]

    def spawn(*args, **kw):
        now[0] = 3
        return Unreaped()

    result = s.supervise(tmp_path.resolve(), 'SYNTHETIC_UNREAPED',
                         popen=spawn, clock=lambda: now[0])
    assert result['first_failure'] == 'MOCK_PHASE_TIMEOUT'
    assert result['phase'] == 'CLEANUP_UNCERTAIN'
    assert result['supervision']['process_cleanup'] == 'UNCONFIRMED'
    assert 'password' not in c.canonical(result).decode()


def test_sticky_failure_and_no_retry_or_fill(tmp_path):
    r = c.mock_receipt('OFF1')
    s.fail(r, 'MOCK_FIRST')
    s.fail(r, 'MOCK_CLEANUP', 'CLEANUP_UNCERTAIN')
    assert r['first_failure'] == 'MOCK_FIRST'
    assert r['failure_reason'] == ['MOCK_FIRST', 'MOCK_CLEANUP']
    receipts = s.batch(tmp_path.resolve(), 'SYNTHETIC_BATCH',
                       scenarios=['nonzero']+['success']*5)
    assert [r['arm_id'] for r in receipts] == ['OFF1']
    assert sorted(p.name for p in tmp_path.iterdir()) == ['SYNTHETIC_BATCH_OFF1']


def test_six_independent_children_in_frozen_order(tmp_path):
    results = s.batch(tmp_path.resolve(), 'SYNTHETIC_SIX')
    assert [r['arm_id'] for r in results] == list(c.ORDER)
    assert all(r['phase'] == 'COMPLETE_MOCK' for r in results)
    assert len(list(tmp_path.iterdir())) == 6
    assert c.statistics(results)['REAL_MEASUREMENT'] is False


@pytest.mark.parametrize('args', [[], ['--real'], ['--root-arm', 'off'], ['--pg'],
                                  ['--worker'], ['--mock', '--module', 'app.jobs'],
                                  ['--mock', '--command', 'echo secret']])
def test_cli_refuses_unsafe_modes_before_temporary_directory(monkeypatch, args):
    monkeypatch.setattr(s.tempfile, 'TemporaryDirectory',
                        lambda **kw: pytest.fail('effects before validation'))
    with pytest.raises(SystemExit) as error:
        s.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize('kwargs', [dict(scenario='--real'), dict(scenario='app.jobs'),
    dict(environment={'DATABASE_URL': 'postgresql://private'}),
    dict(environment={'TOKEN': 'private'}), dict(environment={'HOME': '/Users/private'}),
    dict(environment={'PYTHONPATH': 'app'}), dict(environment={'HOST': 'https://remote'}),
    dict(limits=(1, 1, 180)), dict(limits=(True, 1, 1))])
def test_api_rejects_unapproved_inputs_before_io(tmp_path, kwargs):
    with pytest.raises(c.Refused):
        s.supervise(tmp_path.resolve(), 'SYNTHETIC_BAD', **kwargs)
    assert not list(tmp_path.iterdir())


def test_fixed_command_shell_false_and_no_parent_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'private')
    monkeypatch.setenv('GITHUB_TOKEN', 'private')
    seen = []

    def spawn(args, **kw):
        seen.append((args, copy.deepcopy({k: v for k, v in kw.items() if k != 'pass_fds'})))
        assert args[:3] == [sys.executable, '-m', 'scripts.perf03_lnx_mock_child']
        assert kw['shell'] is False and kw['env'] == s.ENV
        assert 'HOME' not in kw['env'] and 'PATH' not in kw['env']
        assert kw['cwd'] == s.ROOT
        return subprocess.Popen(args, **kw)

    assert s.supervise(tmp_path.resolve(), 'SYNTHETIC_ENV', popen=spawn)['phase'] == 'COMPLETE_MOCK'
    assert len(seen) == 1


@pytest.mark.parametrize('name', ['../ESCAPE', '/tmp/ESCAPE', 'A/B', '.', '', 'https://remote'])
def test_path_traversal_and_absolute_names_refused(tmp_path, name):
    with pytest.raises(c.Refused):
        s.OwnedDirectory(tmp_path.resolve(), name)
    assert not list(tmp_path.iterdir())


def test_duplicate_run_and_arm_refused(tmp_path):
    s.supervise(tmp_path.resolve(), 'SYNTHETIC_DUP')
    with pytest.raises(FileExistsError):
        s.supervise(tmp_path.resolve(), 'SYNTHETIC_DUP')


def test_symlink_leaf_and_file_refused_without_touching_target(tmp_path):
    target = tmp_path/'target'
    target.mkdir()
    (tmp_path/'LINK').symlink_to(target, target_is_directory=True)
    with pytest.raises(FileExistsError):
        s.OwnedDirectory(tmp_path.resolve(), 'LINK')
    sentinel = target/'sentinel'
    sentinel.write_bytes(b'PRIVATE_UNCHANGED')
    with s.OwnedDirectory(tmp_path.resolve(), 'OWNED') as directory:
        (directory.path/'final.json').symlink_to(sentinel)
        with pytest.raises(OSError):
            directory.read('final.json')
        with pytest.raises(FileExistsError):
            directory.write('final.json', c.seal(c.mock_receipt('OFF1')))
    assert sentinel.read_bytes() == b'PRIVATE_UNCHANGED'


def test_replaced_directory_and_archived_content_rejected(tmp_path):
    with s.OwnedDirectory(tmp_path.resolve(), 'OWNED') as directory:
        directory.write('final.json', c.seal(c.mock_receipt('OFF1')))
        raw = c.load((directory.path/'final.json').read_bytes())
        raw['receipt']['metrics']['root_wall_ms'] = '999'
        (directory.path/'final.json').write_bytes(c.canonical(raw))
        with pytest.raises(c.Refused):
            c.unseal(directory.read('final.json'))
        moved = tmp_path/'MOVED'
        directory.path.rename(moved)
        directory.path.mkdir()
        with pytest.raises(c.Refused):
            directory.write('prefix.json', c.seal(c.mock_receipt('OFF1')))
        assert not list(directory.path.iterdir())


def test_symlink_parent_and_non_temp_output_refused(tmp_path):
    target = tmp_path/'target'
    target.mkdir()
    link = tmp_path/'link'
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(c.Refused):
        s.OwnedDirectory(link, 'OWNED')
    with pytest.raises(c.Refused):
        s.OwnedDirectory(Path(__file__).resolve().parents[2], 'OWNED')


def test_unsupported_platform_does_not_degrade_to_global_kill(tmp_path, monkeypatch):
    monkeypatch.setattr(s.sys, 'platform', 'win32')
    with pytest.raises(c.Refused, match='MOCK_PLATFORM_UNSUPPORTED'):
        s.supervise(tmp_path.resolve(), 'SYNTHETIC_WINDOWS')
    assert not list(tmp_path.iterdir())


def test_io_failure_preserves_prefix_and_reports_unavailable(tmp_path, monkeypatch):
    original = s.OwnedDirectory.write

    def fail_final(self, name, value):
        if name == 'final.json':
            raise OSError('private')
        return original(self, name, value)

    monkeypatch.setattr(s.OwnedDirectory, 'write', fail_final)
    result = s.supervise(tmp_path.resolve(), 'SYNTHETIC_IO')
    assert result['phase'] == 'EVIDENCE_UNAVAILABLE'
    assert not result['supervision']['archive_verified']
    assert (tmp_path/'SYNTHETIC_IO_OFF1/prefix.json').exists()


def test_oversized_archive_refused(tmp_path):
    with s.OwnedDirectory(tmp_path.resolve(), 'OWNED') as directory:
        with pytest.raises(c.Refused):
            directory.write('final.json', {'data': 'x'*c.MAX_BYTES})
        assert not (directory.path/'final.json').exists()


def test_raw_secret_fields_cannot_use_archive_writer(tmp_path):
    with s.OwnedDirectory(tmp_path.resolve(), 'OWNED') as directory:
        for value in ({'token': 'PRIVATE'}, {'sql': 'SELECT secret'},
                      {'path': '/Users/private'}, {'dsn': 'postgresql://private'}):
            with pytest.raises(c.Refused):
                directory.write('final.json', value)
        assert not list(directory.path.iterdir())


def test_parent_path_replacement_rejected_by_pinned_identity(tmp_path):
    parent = tmp_path/'parent'
    parent.mkdir()
    with s.OwnedDirectory(parent.resolve(), 'OWNED') as directory:
        parent.rename(tmp_path/'old_parent')
        parent.mkdir()
        with pytest.raises(c.Refused, match='MOCK_PARENT_REPLACED'):
            directory.write('final.json', c.seal(c.mock_receipt('OFF1')))
        assert not list(parent.iterdir())


def test_mock_batch_budget_stops_without_starting_next_child(tmp_path):
    results = s.batch(tmp_path.resolve(), 'SYNTHETIC_LIMIT',
                      scenarios=['no_progress']+['success']*5, window=.05)
    assert len(results) == 1
    assert results[0]['phase'] == 'TIMED_OUT'


def test_cleanup_error_stays_first_and_timeline_is_external(tmp_path):
    r = s.supervise(tmp_path.resolve(), 'SYNTHETIC_CLEAN', scenario='cleanup_failure')
    assert r['first_failure'] == 'MOCK_CLEANUP_FAILED'
    assert 'MOCK_CHILD_INCOMPLETE' in r['failure_reason']
    assert r['cleanup_state'] == 'INCOMPLETE'
    assert [x['phase'] for x in r['supervision']['timeline']] == ['SETUP', 'ROOT', 'CLEANUP']
    assert r['supervision']['deadlines_seconds'] == [180,180,30]


def test_monotonic_clock_reversal_fails_closed(tmp_path):
    now = [2]

    def rollback():
        now[0] = 1

    r = s.supervise(tmp_path.resolve(), 'SYNTHETIC_CLOCK', clock=lambda: now[0],
                    before_start=rollback)
    assert r['phase'] != 'COMPLETE_MOCK'
    assert r['first_failure'] == 'MOCK_CLOCK_REVERSED'


def test_explicit_mock_cli_has_no_real_execution_claim(capsys):
    assert s.main(['--mock']) == 0
    result = c.load(capsys.readouterr().out.encode().strip())
    assert result['REAL_MEASUREMENT'] is False
    assert result['PERFORMANCE_ELIGIBILITY'] == 'NOT_CLAIMED'
    assert not any(result['authorization'].values())


def test_rev1_post_link_read_failure_never_publishes_self_confirming_success(tmp_path, monkeypatch):
    original = s.OwnedDirectory.read

    def failed_read(self, name):
        value = original(self, name)
        if name == 'final.json':
            raise OSError('MOCK injected after successful link')
        return value

    monkeypatch.setattr(s.OwnedDirectory, 'read', failed_read)
    result = s.supervise(tmp_path.resolve(), 'SYNTHETIC_POST_LINK')
    assert result['phase'] == 'EVIDENCE_UNAVAILABLE'
    path = tmp_path/'SYNTHETIC_POST_LINK_OFF1'
    assert (path/'prefix.json').exists()
    raw = c.load((path/'final.json').read_bytes())
    # The original implementation leaves a self-contained sealed COMPLETE_MOCK here.
    assert raw.get('publication') == 'UNCONFIRMED_REQUIRES_OWNER_CONFIRMATION'


@pytest.mark.parametrize('point', ['before_link', 'duplicate_final', 'fsync', 'check', 'read',
                                  'outer_read',
                                  'confirm', 'after_confirm', 'consume'])
def test_rev1_publication_failure_requires_independent_confirmation(tmp_path, monkeypatch, point):
    owner = c.MockConsumptionAuthority()
    confirmations = {}
    linked = [False]
    reads = [0]
    original_link, original_fsync = s.os.link, s.os.fsync
    original_check, original_read = s.OwnedDirectory.check, s.OwnedDirectory.read
    original_confirm = c.MockConsumptionAuthority.confirm

    def link(src, target, **kw):
        if target == 'final.json' and point == 'before_link':
            raise OSError('injected before link')
        if target == 'final.json' and point == 'duplicate_final':
            original_link(src, target, **kw)
        result = original_link(src, target, **kw)
        if target == 'final.json':
            linked[0] = True
        return result

    def fsync(fd):
        if linked[0] and point == 'fsync':
            raise OSError('injected fsync')
        return original_fsync(fd)

    def check(self):
        if linked[0] and point == 'check':
            raise OSError('injected post-link check')
        return original_check(self)

    def read(self, name):
        if name == 'final.json':
            reads[0] += 1
            if point == 'read' or (point == 'outer_read' and reads[0] == 2):
                raise OSError('injected post-link read')
        return original_read(self, name)

    def confirm(self, value):
        if point == 'confirm':
            raise OSError('injected confirmation')
        token = original_confirm(self, value)
        if point == 'after_confirm':
            raise OSError('lost confirmation reply')
        return token

    monkeypatch.setattr(s.os, 'link', link)
    monkeypatch.setattr(s.os, 'fsync', fsync)
    monkeypatch.setattr(s.OwnedDirectory, 'check', check)
    monkeypatch.setattr(s.OwnedDirectory, 'read', read)
    monkeypatch.setattr(c.MockConsumptionAuthority, 'confirm', confirm)
    if point == 'consume':
        monkeypatch.setattr(c, 'consume_final', lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    result = s.supervise(tmp_path.resolve(), 'SYNTHETIC_PUBLISH', authority=owner,
                         confirmations=confirmations)
    assert result['phase'] == 'EVIDENCE_UNAVAILABLE'
    assert result['first_failure'] == 'MOCK_EVIDENCE_UNAVAILABLE'
    assert not result['supervision']['archive_verified']
    assert not confirmations and not owner._tickets and not owner._pending
    c.validate_receipt(result)
    path = tmp_path/'SYNTHETIC_PUBLISH_OFF1'
    prefix = (path/'prefix.json').read_bytes()
    assert c.unseal(c.load(prefix))['phase'] == 'INCOMPLETE'
    if point == 'before_link':
        assert not (path/'final.json').exists()
    else:
        raw = c.load((path/'final.json').read_bytes())
        assert raw['publication'] == c.UNCONFIRMED
        assert c.unseal(raw)['phase'] == 'COMPLETE_MOCK'  # Candidate, NOT final acceptance.
        # Even an owner object/new reader cannot reconstruct an aborted scope from the file.
        fresh = c.MockConsumptionAuthority()
        fresh.begin('SYNTHETIC_PUBLISH', 'OFF1')
        with pytest.raises(c.Refused):
            original_confirm(fresh, raw)
        with pytest.raises(c.Refused):
            original_confirm(owner, raw)


def test_rev1_normal_consumer_needs_live_owner_ticket_and_exact_candidate(tmp_path):
    owner, tickets = c.MockConsumptionAuthority(), {}
    r = s.supervise(tmp_path.resolve(), 'SYNTHETIC_CONFIRMED', authority=owner,
                    confirmations=tickets)
    raw = c.load((tmp_path/'SYNTHETIC_CONFIRMED_OFF1/final.json').read_bytes())
    ticket = tickets[('SYNTHETIC_CONFIRMED', 'OFF1')]
    assert c.consume_final(raw, authority=owner, confirmation=ticket) == r
    assert r['phase'] == 'COMPLETE_MOCK'
    assert not any(r['authorization'].values())
    with pytest.raises(c.Refused):
        c.consume_final(raw)
    with pytest.raises(c.Refused):
        c.consume_final(raw, authority=c.MockConsumptionAuthority(), confirmation=ticket)
    with pytest.raises(c.Refused):
        c.consume_final(raw, authority=owner, confirmation={'hash': raw['sha256']})
    changed = copy.deepcopy(raw)
    changed['receipt']['metrics']['root_wall_ms'] = '101'
    changed['sha256'] = c.digest(changed['receipt'])
    with pytest.raises(c.Refused):
        c.consume_final(changed, authority=owner, confirmation=ticket)


def test_rev1_error_before_archive_keeps_first_failure(tmp_path, monkeypatch):
    original = s.OwnedDirectory.write

    def broken_final(self, name, value):
        if name == 'final.json':
            raise OSError('later archive failure')
        return original(self, name, value)

    monkeypatch.setattr(s.OwnedDirectory, 'write', broken_final)
    r = s.supervise(tmp_path.resolve(), 'SYNTHETIC_STICKY', scenario='nonzero')
    assert r['phase'] == 'EVIDENCE_UNAVAILABLE'
    assert r['first_failure'] == 'MOCK_CHILD_EXIT'
    assert r['failure_reason'] == ['MOCK_CHILD_EXIT', 'MOCK_EVIDENCE_UNAVAILABLE']
    c.validate_receipt(r)


def test_rev1_close_error_revokes_scope_without_rewriting_candidate(tmp_path, monkeypatch):
    owner, tickets = c.MockConsumptionAuthority(), {}
    original = s.OwnedDirectory.close

    def failed_close(self):
        original(self)
        if (self.path/'final.json').exists():
            raise OSError('injected close after actual close')

    monkeypatch.setattr(s.OwnedDirectory, 'close', failed_close)
    with pytest.raises(OSError):
        s.supervise(tmp_path.resolve(), 'SYNTHETIC_CLOSE', authority=owner, confirmations=tickets)
    assert not tickets and not owner._tickets and not owner._pending
    raw = c.load((tmp_path/'SYNTHETIC_CLOSE_OFF1/final.json').read_bytes())
    assert raw['publication'] == c.UNCONFIRMED
    with pytest.raises(c.Refused):
        c.consume_final(raw, authority=owner)


@pytest.mark.parametrize('point', ['popen', 'prefix_io', 'fsync'])
def test_rev1_synchronous_blocking_call_is_not_hard_preempted(tmp_path, monkeypatch, point):
    observed = []
    original_write = s.OwnedDirectory.write
    original_fsync = s.os.fsync

    def slow_spawn(*args, **kw):
        observed.append('entered')
        time.sleep(.025)
        observed.append('returned')
        return subprocess.Popen(*args, **kw)

    def slow_write(self, name, value):
        if name == 'prefix.json':
            observed.append('entered')
            time.sleep(.025)
            observed.append('returned')
        return original_write(self, name, value)

    def slow_fsync(fd):
        if not observed:
            observed.append('entered')
            time.sleep(.025)
            observed.append('returned')
        return original_fsync(fd)

    if point == 'prefix_io':
        monkeypatch.setattr(s.OwnedDirectory, 'write', slow_write)
    if point == 'fsync':
        monkeypatch.setattr(s.os, 'fsync', slow_fsync)
    began = time.monotonic()
    r = s.supervise(tmp_path.resolve(), 'SYNTHETIC_BLOCKING', limits=(.01, .01, .01),
                    popen=slow_spawn if point == 'popen' else subprocess.Popen)
    elapsed = time.monotonic() - began
    assert elapsed >= .025  # No preemption at the .01 deadline inside the synchronous call.
    assert observed == ['entered', 'returned']
    assert r['phase'] != 'COMPLETE_MOCK'
    assert r['first_failure'] in {'MOCK_START_TIMEOUT', 'MOCK_PHASE_TIMEOUT'}
