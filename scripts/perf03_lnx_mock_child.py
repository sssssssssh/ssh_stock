"""Bounded artificial child. No application, native extensions, DB or subprocess imports."""

import argparse
import os
import time

from scripts import perf03_lnx_offline_contract as c


def emit(fd, name, value):
    raw = c.canonical(value)
    pending = 'pending_' + name
    descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(pending, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
    finally:
        os.unlink(pending, dir_fd=fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=int, required=True)
    parser.add_argument('--arm', choices=c.ORDER, required=True)
    parser.add_argument('--scenario', required=True, choices=(
        'success', 'no_progress', 'setup_hang', 'root_hang', 'cleanup_hang', 'crash',
        'nonzero', 'no_report', 'bad_json', 'bad_order', 'early_complete',
        'cleanup_failure', 'native_exit', 'wrong_sha', 'oversize'))
    args = parser.parse_args(argv)
    if args.scenario in {'no_progress', 'setup_hang'}:
        time.sleep(4)  # Hard child bound even without the parent.
        return 2
    if args.scenario in {'crash', 'native_exit'}:
        # Exit is simulated, NOT a native exception or real crash measurement.
        os._exit(139 if args.scenario == 'native_exit' else 7)
    if args.scenario == 'early_complete':
        emit(args.fd, '3.json', c.seal(c.mock_receipt(args.arm)))
        time.sleep(4)
        return 0
    for index, phase in enumerate(('SETUP', 'ROOT', 'CLEANUP')):
        if (phase == 'ROOT' and args.scenario == 'root_hang') or (
                phase == 'CLEANUP' and args.scenario == 'cleanup_hang'):
            time.sleep(4)
            return 2
        emit(args.fd, str(index) + '.json', {'phase': 'ROOT' if
             args.scenario == 'bad_order' and index == 0 else phase})
    if args.scenario == 'nonzero':
        return 3
    if args.scenario == 'no_report':
        return 0
    if args.scenario in {'bad_json', 'oversize'}:
        descriptor = os.open('3.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                             0o600, dir_fd=args.fd)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(b'{' if args.scenario == 'bad_json' else b' ' * (c.MAX_BYTES + 1))
        return 0
    receipt = c.mock_receipt(args.arm)
    if args.scenario == 'wrong_sha':
        receipt['identity']['source_sha'] = 'f' * 40
    if args.scenario == 'cleanup_failure':
        receipt.update(cleanup_state='INCOMPLETE', phase='CLEANUP_UNCERTAIN',
                       final_receipt_status='CLEANUP_UNCERTAIN',
                       first_failure='MOCK_CLEANUP_FAILED', failure_reason=['MOCK_CLEANUP_FAILED'])
    emit(args.fd, '3.json', c.seal(receipt))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
