"""Standalone installed worker loader. FD3 is root-sealed; no CLI/env activation."""

import fcntl
import hashlib
import json
import os
import stat
import sys


def main():
    # No repository import before the installed archive is independently hashed.
    if len(sys.argv) != 1:
        return 78
    meta = os.fstat(3)
    seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_WRITE
    if not (
        stat.S_ISREG(meta.st_mode)
        and meta.st_uid == 0
        and meta.st_mode & 0o777 == 0o400
        and 0 < meta.st_size <= 65536
    ):
        return 78
    body = json.loads(os.pread(3, 65537, 0))
    worker = body.get("version") == "a42364.worker-capsule.v3"
    if worker and fcntl.fcntl(3, fcntl.F_GET_SEALS) & seals != seals:
        return 78
    if not worker and (
        body.get("version") != "a42364.installation.v3"
        or meta.st_nlink != 1
        or fcntl.fcntl(3, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY
    ):
        return 78
    fd = os.open("/opt/space-g1/source.zip", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        original = os.fstat(fd)
        if not (
            stat.S_ISREG(original.st_mode)
            and original.st_uid == 0
            and original.st_mode & 0o022 == 0
            and original.st_nlink == 1
            and 0 < original.st_size <= 16_000_000
        ):
            return 78
        digest = hashlib.sha256()
        offset = 0
        while offset < original.st_size:
            chunk = os.pread(fd, min(65536, original.st_size - offset), offset)
            if not chunk:
                return 78
            digest.update(chunk)
            offset += len(chunk)
        expected = body.get("source_archive_sha256") if worker else body.get("code_archive_sha256")
        if digest.hexdigest() != expected:
            return 78
        current = os.fstat(fd)
        if (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
        ) != (
            original.st_dev,
            original.st_ino,
            original.st_size,
            original.st_mtime_ns,
            original.st_ctime_ns,
        ):
            return 78
        sys.path.insert(0, "/proc/self/fd/" + str(fd))
        from scripts.a42364_manager import run_worker_capsule, serve_installed

        if worker:
            run_worker_capsule(3)
        else:
            serve_installed(3, 5)
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:
        code = 78  # No credential-bearing exception/traceback on stdout/stderr.
    raise SystemExit(code)
