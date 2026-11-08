"""Fixed Linux mock actor, never a business execution or arbitrary-command adapter."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Isolated -I -S script: only its fixed peer directory is made importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import perf03_lnx_hard_watchdog as w  # noqa: E402


def emit(fd, spec, event, child_pid=None, **detail):
    value = dict(v=1, run_id=spec['run_id'], spec_sha256=w.spec_hash(spec),
        pid=os.getpid(), pgid=os.getpgrp(), event=event, child_pid=child_pid)
    value.update(detail)
    raw = w.canonical(value) + b'\n'
    w.require(len(raw) <= 1024)
    w.require(os.write(fd, raw) == len(raw), 'HARD_MOCK_PROTOCOL')


def simulated_block(*_args, **_kwargs):
    time.sleep(5)  # Explicitly SIMULATED, never evidence of an actual fsync/Popen deadlock.



class ChildLifecycle:
    """One fixed child, one creation attempt, one frozen cleanup decision."""

    def __init__(self):
        self.child = None
        self.state = 'NOT_STARTED'
        self.first_failure = None
        self.errors = []
        self.actions = []
        self.result = None
        self.creation_attempted = False

    def refused(self, code):
        if self.first_failure is None:
            self.first_failure = code
        if code not in self.errors:
            self.errors.append(code)
        self.state = 'OWNERSHIP_UNCONFIRMED'

    def create(self, args, spec, stopped):
        w.require(not self.creation_attempted and self.state == 'NOT_STARTED'
                  and self.result is None)
        w.validate_request(spec)
        w.require(spec['scenario'] in w.CHILD_SCENARIOS)
        self.creation_attempted = True
        if stopped[0]:
            return
        self.state = 'CREATING'
        try:
            # The kernel assigns the actor's own PGID before exec. The fixed child
            # never sets a new session/group; no caller PID/PGID is accepted.
            self.child = subprocess.Popen([sys.executable, '-I', '-S',
                str(Path(__file__).resolve()), '--mock', '--run-id', spec['run_id'],
                '--scenario', spec['scenario'], '--timeout-ms', str(spec['timeout_ms']),
                '--pipe-fd', str(args.pipe_fd), '--directory-fd', str(args.directory_fd),
                '--same-group-child'], shell=False, start_new_session=False,
                process_group=os.getpgrp(), env=w.ENV.copy(), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if self.child is None:
                self.refused('HARD_MOCK_CHILD_START_UNKNOWN')
            else:
                self.state = 'OWNED'
                if spec['scenario'] == 'child_term_before_registration':
                    os.kill(os.getpid(), signal.SIGTERM)
        except (OSError, KeyboardInterrupt):
            # A constructor exception without a handle is NOT proof no child exists.
            self.refused('HARD_MOCK_CHILD_START_UNKNOWN')

    def _identity(self):
        child = self.child
        w.require(type(child.pid) is int and child.pid > 1
                  and getattr(child, 'returncode', None) is None,
                  'HARD_MOCK_CHILD_IDENTITY')
        group = os.getpgrp()
        w.require(group > 1 and os.getsid(child.pid) == group, 'HARD_MOCK_CHILD_IDENTITY')
        # Group membership was explicitly set by the successful fixed Popen call.
        # watchdog independently checks getpgid while live and final group absence.

    def _freeze(self, code=None):
        if code is not None and type(code) is not int:
            self.refused('HARD_MOCK_CHILD_EXIT_INVALID')
            code = None
        if self.state != 'NOT_STARTED':
            self.state = 'REAPED' if code is not None and not self.errors else \
                'OWNERSHIP_UNCONFIRMED'
        self.result = dict(state=self.state, child_exit_code=code,
            first_failure=self.first_failure, cleanup_errors=tuple(self.errors),
            actions=tuple(self.actions))
        return self.result.copy()

    def cleanup(self):
        if self.result is not None:
            return self.result.copy()
        if self.child is None:
            if self.state != 'NOT_STARTED':
                self.refused('HARD_MOCK_CHILD_START_UNKNOWN')
            return self._freeze()
        # One absolute 0.1s cleanup budget, equal to the original wait bound.
        began = time.monotonic()
        term_end, end = began + .05, began + .1
        try:
            # If already exited, reap once and never signal its now-reusable PID.
            try:
                return self._freeze(self.child.wait(timeout=0))
            except subprocess.TimeoutExpired:
                pass
            self._identity()
            self.child.terminate()
            self.actions.append('TERM')
            try:
                return self._freeze(self.child.wait(timeout=max(0., term_end-time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
            self._identity()
            w.require(time.monotonic() < end, 'HARD_MOCK_CHILD_BUDGET')
            self.child.kill()
            self.actions.append('KILL')
            return self._freeze(self.child.wait(timeout=max(0., end-time.monotonic())))
        except (OSError, KeyboardInterrupt, subprocess.TimeoutExpired, w.Refused) as error:
            self.refused(str(error) if isinstance(error, w.Refused)
                         else 'HARD_MOCK_CHILD_CLEANUP')
            return self._freeze()


def same_group_child(args, spec, stopped):
    owner = ChildLifecycle()
    if spec['scenario'] == 'child_term_before_spawn':
        os.kill(os.getpid(), signal.SIGTERM)
    owner.create(args, spec, stopped)
    child = owner.child
    try:
        if child is not None:
            emit(args.pipe_fd, spec, 'CHILD', child.pid)
        if spec['scenario'] == 'child_term_after_spawn':
            os.kill(os.getpid(), signal.SIGTERM)
        if child is not None and owner.state == 'OWNED':
            while not stopped[0] and not w._exited(child):
                time.sleep(.002)
        # Handler only registers intent; IPC failures must also run owned cleanup.
        if stopped[0]:
            emit(args.pipe_fd, spec, 'TERM_REQUESTED', child.pid if child else None)
    except (OSError, ChildProcessError, KeyboardInterrupt):
        owner.refused('HARD_MOCK_CHILD_WAIT_UNKNOWN')
    finally:
        result = owner.cleanup()
    if result['state'] == 'NOT_STARTED':
        emit(args.pipe_fd, spec, 'CHILD_NOT_STARTED')
    elif result['state'] == 'REAPED':
        emit(args.pipe_fd, spec, 'CHILD_REAPED', child.pid,
             child_exit_code=result['child_exit_code'])
    else:
        emit(args.pipe_fd, spec, 'CHILD_UNCONFIRMED', child.pid if child else None,
             child_failure=result['first_failure'], cleanup_errors=result['cleanup_errors'])
        return 2
    emit(args.pipe_fd, spec, 'DONE', child.pid if child else None)
    # Successful cleanup is NOT an assertion of successful work; TERM is in the protocol.
    return 0 if stopped[0] or result['child_exit_code'] == 0 else 2

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mock', action='store_true', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--scenario', choices=w.SCENARIOS, required=True)
    parser.add_argument('--timeout-ms', type=int, required=True)
    parser.add_argument('--pipe-fd', type=int, required=True)
    parser.add_argument('--directory-fd', type=int, required=True)
    parser.add_argument('--same-group-child', action='store_true')
    args = parser.parse_args(argv)
    spec = w.request(args.scenario, run_id=args.run_id, timeout_ms=args.timeout_ms)
    w.require(sys.platform == 'linux' and args.pipe_fd > 2 and args.directory_fd > 2)
    if args.same_group_child:
        w.require(args.scenario in w.CHILD_SCENARIOS)
        time.sleep(5)  # TERM defaults to termination; actor parent must wait/reap us.
        return 0
    w.require(os.getpid() == os.getpgrp() == os.getsid(0), 'HARD_MOCK_OWNERSHIP')
    scenario = args.scenario
    if scenario in {'ignore_term', 'late_success'}:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # Only this private actor, never pytest.
    stopped = [False]
    if scenario in w.CHILD_SCENARIOS:
        def term(_signum, _frame):
            stopped[0] = True
        signal.signal(signal.SIGTERM, term)
    emit(args.pipe_fd, spec, 'READY')
    if scenario == 'block_fifo_open':
        os.mkfifo('block.fifo', mode=0o600, dir_fd=args.directory_fd)
        fd = os.open('block.fifo', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=args.directory_fd)
        os.close(fd)
    elif scenario.startswith('block_'):
        operation = {'block_popen_simulated': 'popen', 'block_fsync_simulated': 'fsync',
                     'block_prefix_write_simulated': 'write', 'block_read_simulated': 'read',
                     'block_link_simulated': 'link', 'block_close_simulated': 'close'}[scenario]
        if operation == 'popen':
            subprocess.Popen = simulated_block
            subprocess.Popen()
        else:
            setattr(os, operation, simulated_block)
            getattr(os, operation)(args.directory_fd)
    elif scenario in {'ignore_term', 'late_success'}:
        time.sleep(5)
    elif scenario in w.CHILD_SCENARIOS:
        return same_group_child(args, spec, stopped)
    elif scenario == 'bad_receipt':
        os.write(args.pipe_fd, b'{"event":"PRIVATE_INVALID"}\n')
        return 0
    elif scenario == 'nonzero':
        return 7
    elif scenario == 'missing_receipt':
        return 0
    emit(args.pipe_fd, spec, 'DONE')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
