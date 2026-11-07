"""Fixed mock child only. No real execution adapter, application imports or network."""

import argparse
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from scripts import perf03_lnx_offline_contract as c

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = frozenset({'success', 'no_progress', 'setup_hang', 'root_hang', 'cleanup_hang',
    'crash', 'nonzero', 'no_report', 'bad_json', 'bad_order', 'early_complete',
    'cleanup_failure', 'native_exit', 'wrong_sha', 'oversize'})
ENV = {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'}


class OwnedDirectory:
    """An exclusively created leaf held by dirfd; validate inode on every I/O.

    Ancestors must already exist, belong to this user and be free of symlinks.
    The temporary root is an explicit trust anchor, never an arbitrary output path.
    """

    def __init__(self, parent, name):
        c.require(sys.platform in {'darwin', 'linux'}, 'MOCK_PLATFORM_UNSUPPORTED')
        c.require(type(name) is str and re.fullmatch(r'[A-Z][A-Z0-9_]{0,50}', name) is not None)
        parent = Path(parent)
        c.require(parent.is_absolute() and '..' not in parent.parts)
        trusted = Path(tempfile.gettempdir()).resolve()
        resolved = parent.resolve(strict=True)
        c.require(resolved.is_relative_to(trusted) and resolved != trusted)
        # The system temp path itself may have a platform alias (/var on macOS).
        current = trusted
        for part in resolved.relative_to(trusted).parts:
            current /= part
            c.require(not current.is_symlink())
        c.require(parent == resolved, 'MOCK_PATH_ALIAS_REFUSED')
        self.parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.fd = None
        self.path = parent / name
        self.parent_path = parent
        self.name = name
        try:
            c.require(os.fstat(self.parent_fd).st_uid == os.getuid())
            os.mkdir(name, mode=0o700, dir_fd=self.parent_fd)
            self.fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=self.parent_fd)
            self.identity = os.fstat(self.fd)
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        parent = os.stat(self.parent_path, follow_symlinks=False)
        expected = os.fstat(self.parent_fd)
        c.require(stat.S_ISDIR(parent.st_mode) and
                  (parent.st_dev, parent.st_ino) == (expected.st_dev, expected.st_ino),
                  'MOCK_PARENT_REPLACED')
        actual = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
        c.require(stat.S_ISDIR(actual.st_mode) and
                  (actual.st_dev, actual.st_ino) == (self.identity.st_dev, self.identity.st_ino),
                  'MOCK_DIRECTORY_REPLACED')

    def write(self, name, value):
        c.require(name in {'prefix.json', 'final.json'}, 'MOCK_PATH_REFUSED')
        self.check()
        c.unseal(value)  # Only registered, sanitized mock receipts can be exported.
        raw = c.canonical(value)
        c.require(len(raw) <= c.MAX_BYTES)
        pending = 'stage_' + uuid.uuid4().hex
        descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=self.fd)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            self.check()
            os.link(pending, name, src_dir_fd=self.fd, dst_dir_fd=self.fd,
                    follow_symlinks=False)
            os.unlink(pending, dir_fd=self.fd)
            self.check()
            os.fsync(self.fd)
            c.require(self.read(name) == value, 'MOCK_ARCHIVE_MISMATCH')
        finally:
            try:
                os.unlink(pending, dir_fd=self.fd)
            except FileNotFoundError:
                pass

    def read(self, name):
        c.require(name in {'prefix.json', 'final.json', '0.json', '1.json', '2.json', '3.json'})
        self.check()
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        with os.fdopen(descriptor, 'rb') as handle:
            info = os.fstat(handle.fileno())
            c.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                      and info.st_nlink == 1 and info.st_size <= c.MAX_BYTES)
            raw = handle.read(c.MAX_BYTES + 1)
            end = os.fstat(handle.fileno())
            current = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            c.require((info.st_ino, info.st_size, info.st_mtime_ns) ==
                      (end.st_ino, end.st_size, end.st_mtime_ns)
                      and (info.st_dev, info.st_ino) == (current.st_dev, current.st_ino),
                      'MOCK_FILE_REPLACED')
        self.check()
        return c.load(raw)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if getattr(self, 'parent_fd', None) is not None:
            os.close(self.parent_fd)
            self.parent_fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def fail(receipt, code, state='FAILED'):
    if code not in receipt['failure_reason'] and len(receipt['failure_reason']) < 10:
        receipt['failure_reason'].append(code)
    receipt['first_failure'] = receipt['failure_reason'][0]
    receipt['phase'] = receipt['final_receipt_status'] = state


def _supervise_registered(parent, run_id, arm='OFF1', *, scenario='success', limits=(1, 1, 1),
              environment=None, clock=time.monotonic, popen=subprocess.Popen,
              before_start=None, batch_deadline=None, authority=None, confirmations=None,
              confirmation_scope=None):
    """Mock phase supervision, NOT a hard deadline for blocking Popen/filesystem calls."""
    c.require(type(scenario) is str and scenario in SCENARIOS
              and type(arm) is str and arm in c.ORDER, 'MOCK_ENTRY_REFUSED')
    c.require(environment is None or environment == ENV, 'MOCK_ENVIRONMENT_REFUSED')
    c.require(type(run_id) is str and re.fullmatch(r'SYNTHETIC_[A-Z0-9_]{1,30}', run_id)
              is not None, 'MOCK_RUN_ID_REFUSED')
    c.require(type(limits) in (list, tuple) and len(limits) == 3
              and all(type(x) in (int, float) and 0 < x <= 1 for x in limits))
    c.require(authority is None or type(authority) is c.MockConsumptionAuthority)
    c.require(confirmations is None or (type(confirmations) is dict
              and (run_id, arm) not in confirmations))
    authority = authority if authority is not None else c.MockConsumptionAuthority()
    started = clock()
    receipt = c.mock_receipt(arm)
    receipt['identity']['run_id'] = run_id
    receipt['phase'] = receipt['final_receipt_status'] = 'INCOMPLETE'
    receipt['cleanup_state'] = 'NOT_ASSESSED'
    receipt['child_exit_code'] = None
    receipt['supervision'].update(phases=[], mock_deadlines_seconds=list(limits))
    process = None
    prepared = None
    with OwnedDirectory(parent, run_id + '_' + arm) as directory:
        directory.write('prefix.json', c.seal(receipt))
        phase = 0
        phase_began = started
        deadline = started + limits[0]
        if batch_deadline is not None:
            deadline = min(deadline, batch_deadline)
        try:
            if before_start is not None:
                before_start()
            c.require(clock() < deadline, 'MOCK_START_TIMEOUT')
            command = [sys.executable, '-m', 'scripts.perf03_lnx_mock_child',
                '--fd', str(directory.fd), '--scenario', scenario, '--arm', arm]
            process = popen(command, shell=False, cwd=ROOT, env=ENV.copy(),
                pass_fds=(directory.fd,), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True)
            while True:
                directory.check()
                c.require(clock() >= phase_began, 'MOCK_CLOCK_REVERSED')
                if clock() >= deadline:
                    fail(receipt, 'MOCK_PHASE_TIMEOUT', 'TIMED_OUT')
                    break
                if phase < 3:
                    try:
                        event = directory.read(str(phase) + '.json')
                    except FileNotFoundError:
                        event = None
                    if event is not None:
                        c.exact(event, ('phase',))
                        c.require(event['phase'] == ('SETUP', 'ROOT', 'CLEANUP')[phase],
                                  'MOCK_PHASE_ORDER')
                        now = clock()
                        c.require(phase_began <= now < deadline, 'MOCK_PHASE_TIMEOUT')
                        receipt['supervision']['phases'].append(event['phase'])
                        receipt['supervision']['timeline'].append(dict(phase=event['phase'],
                            began=format(phase_began, '.9f'), deadline=format(deadline, '.9f'),
                            ended=format(now, '.9f'), complete=True))
                        phase += 1
                        # ROOT starts after SETUP-complete; CLEANUP after ROOT-complete.
                        if phase < 3:
                            phase_began = now
                            deadline = now + limits[phase]
                        if batch_deadline is not None:
                            deadline = min(deadline, batch_deadline)
                        continue
                code = process.poll()
                if code is not None:
                    receipt['child_exit_code'] = code
                    if code != 0:
                        fail(receipt, 'MOCK_CHILD_EXIT', 'CRASHED' if
                             code < 0 or code in {7, 139} else 'FAILED')
                        break
                    c.require(phase == 3, 'MOCK_PHASE_MISSING')
                    child = c.unseal(directory.read('3.json'))
                    c.require(child['arm_id'] == arm and child['identity'] ==
                              {**receipt['identity'], 'run_id': 'SYNTHETIC_NO_PG'},
                              'MOCK_CHILD_IDENTITY')
                    for key in ('business_snapshot', 'metrics', 'job_state', 'publication_state',
                                'ack_state', 'timestamps', 'cleanup_state'):
                        receipt[key] = child[key]
                    if child['phase'] != 'COMPLETE_MOCK':
                        for reason in child['failure_reason']:
                            fail(receipt, reason, child['phase'])
                        c.require(False, 'MOCK_CHILD_INCOMPLETE')
                    receipt['cleanup_state'] = child['cleanup_state']
                    receipt['phase'] = receipt['final_receipt_status'] = 'COMPLETE_MOCK'
                    break
                time.sleep(.002)
        except KeyboardInterrupt:
            fail(receipt, 'MOCK_PARENT_INTERRUPTED', 'INCOMPLETE')
        except c.Refused as error:
            fail(receipt, str(error), receipt['phase'] if receipt['first_failure'] else 'FAILED')
        except (OSError, ValueError, TypeError, KeyError):
            fail(receipt, 'MOCK_EVIDENCE_INVALID')
        finally:
            if phase < 3:
                receipt['supervision']['timeline'].append(dict(
                    phase=('SETUP', 'ROOT', 'CLEANUP')[phase],
                    began=format(phase_began, '.9f'), deadline=format(deadline, '.9f'),
                    ended=format(max(phase_began, clock()), '.9f'), complete=False))
            try:
                if process is not None:
                    if process.poll() is None:
                        # Only our Popen handle; no PID input or process/group scan.
                        process.kill()
                    process.wait(timeout=.5)
                    c.require(process.poll() is not None, 'MOCK_PROCESS_UNCONFIRMED')
                    receipt['child_exit_code'] = process.returncode
                    receipt['supervision']['child_reaped'] = True
                receipt['supervision']['process_cleanup'] = 'REAPED'
            except (OSError, subprocess.TimeoutExpired, c.Refused):
                receipt['supervision']['process_cleanup'] = 'UNCONFIRMED'
                receipt['cleanup_state'] = 'INCOMPLETE'
                fail(receipt, 'MOCK_PROCESS_UNCONFIRMED', 'CLEANUP_UNCERTAIN')
            receipt['supervision']['parent_verified'] = True
            receipt['supervision']['observed_elapsed_seconds'] = format(
                max(0, clock() - started), '.6f')
        # An exit observed after the deadline may not claim a successful arm.
        if clock() >= deadline and receipt['phase'] == 'COMPLETE_MOCK':
            fail(receipt, 'MOCK_PHASE_TIMEOUT', 'TIMED_OUT')
        try:
            receipt['supervision']['archive_verified'] = True
            c.validate_receipt(receipt, supervised=True)
            directory.write('final.json', c.seal(receipt, confirmation_scope=confirmation_scope))
            prepared = directory.read('final.json')
            c.require(c.unseal(prepared, expected_sha256=c.digest(receipt)) == receipt)
        except (OSError, c.Refused):
            prepared = None
            receipt['supervision']['archive_verified'] = False
            fail(receipt, 'MOCK_EVIDENCE_UNAVAILABLE', 'EVIDENCE_UNAVAILABLE')
    # No ticket is issued until all publication I/O AND directory FD close returned.
    # A leftover final.json is always UNCONFIRMED, including after a post-link failure.
    if prepared is not None and receipt['phase'] == 'COMPLETE_MOCK':
        ticket = None
        try:
            ticket = authority.confirm(prepared)
            accepted = c.consume_final(prepared, authority=authority, confirmation=ticket)
            c.require(accepted == receipt)
            if confirmations is not None:
                confirmations[(run_id, arm)] = ticket
        except (OSError, c.Refused):
            authority.revoke(ticket)
            receipt['supervision']['archive_verified'] = False
            fail(receipt, 'MOCK_EVIDENCE_UNAVAILABLE', 'EVIDENCE_UNAVAILABLE')
    return receipt


def supervise(parent, run_id, arm='OFF1', *, scenario='success', limits=(1, 1, 1),
              environment=None, clock=time.monotonic, popen=subprocess.Popen,
              before_start=None, batch_deadline=None, authority=None, confirmations=None):
    """Register a fresh owner scope BEFORE publication; revoke on every failed exit."""
    c.require(authority is None or type(authority) is c.MockConsumptionAuthority)
    authority = authority if authority is not None else c.MockConsumptionAuthority()
    scope = authority.begin(run_id, arm)
    try:
        result = _supervise_registered(parent, run_id, arm, scenario=scenario, limits=limits,
            environment=environment, clock=clock, popen=popen, before_start=before_start,
            batch_deadline=batch_deadline, authority=authority, confirmations=confirmations,
            confirmation_scope=scope)
        if result['phase'] != 'COMPLETE_MOCK':
            authority.revoke_scope(scope)
        return result
    except BaseException:
        authority.revoke_scope(scope)
        raise


def batch(parent, run_id, *, scenarios=None, clock=time.monotonic, window=10):
    c.require(type(window) in (int, float) and 0 < window <= 10)
    c.require(scenarios is None or (type(scenarios) is list and len(scenarios) == 6
              and all(s in SCENARIOS for s in scenarios)))
    deadline = clock() + window
    receipts = []
    for index, arm in enumerate(c.ORDER):
        receipt = supervise(parent, run_id, arm,
            scenario=scenarios[index] if scenarios else 'success',
            clock=clock, batch_deadline=deadline)
        receipts.append(receipt)
        if receipt['phase'] != 'COMPLETE_MOCK':
            break
    return receipts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mock', action='store_true', required=True)
    parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='perf03_mock_') as parent:
        receipts = batch(Path(parent).resolve(), 'SYNTHETIC_' + uuid.uuid4().hex[:24].upper())
        if len(receipts) != 6 or any(r['phase'] != 'COMPLETE_MOCK' for r in receipts):
            print('MOCK_INCOMPLETE_NOT_REAL_MEASUREMENT')
            return 2
        print(c.canonical(c.statistics(receipts)).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
