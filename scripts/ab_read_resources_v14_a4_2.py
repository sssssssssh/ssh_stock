"""Synthetic-instance resource samples; counters are labelled by attribution scope."""

import ctypes
import os
import sys
import threading
from pathlib import Path


def host_memory_bytes():
    if sys.platform == "win32":
        class Memory(ctypes.Structure):
            _fields_ = [("length",ctypes.c_ulong),("load",ctypes.c_ulong),
                        *[(name,ctypes.c_ulonglong) for name in (
                            "total", "available", "page", "available_page",
                            "virtual", "available_virtual", "extended")]]

        value = Memory()
        value.length = ctypes.sizeof(value)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            raise OSError("A42_HOST_MEMORY_SAMPLE_FAILED")
        return value.total
    return os.sysconf("SC_PHYS_PAGES")*os.sysconf("SC_PAGE_SIZE")


def cpu_sample(pid):
    if sys.platform == "win32":
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        file = wintypes.FILETIME
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(file)]*4))
        kernel.GetSystemTimes.argtypes = (ctypes.POINTER(file),)*3
        values = [file() for _ in range(4)]
        host = [file() for _ in range(3)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        try:
            if not handle or not kernel.GetProcessTimes(handle, *map(ctypes.byref, values)):
                raise OSError("A42_PROCESS_CPU_SAMPLE_FAILED")
            if not kernel.GetSystemTimes(*map(ctypes.byref, host)):
                raise OSError("A42_HOST_CPU_SAMPLE_FAILED")
        finally:
            if handle:
                kernel.CloseHandle(handle)

        def seconds(item):
            return ((item.dwHighDateTime<<32)+item.dwLowDateTime)/10000000

        return {"backend_cpu_seconds": sum(map(seconds, values[2:])),
                "host_idle_seconds": seconds(host[0]),
                "host_total_seconds": sum(map(seconds, host[1:]))}
    values = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    ticks = os.sysconf("SC_CLK_TCK")
    host = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:]))
    return {"backend_cpu_seconds": (int(values[11])+int(values[12]))/ticks,
            "host_idle_seconds": sum(host[3:5])/ticks, "host_total_seconds": sum(host[:8])/ticks}


class Telemetry:
    def __init__(self, engine, pid, readers=0, *, container=False):
        from sqlalchemy import create_engine

        from scripts.publication_candidate_benchmark_v13 import ReaderProbe

        self.engine = create_engine(engine.url, hide_parameters=True)
        self.pid, self.stop = pid, threading.Event()
        self.container = container
        self.waits, self.errors, self.cpu = [], [], []
        self.reader = ReaderProbe(engine, readers)

    def sample(self):
        from sqlalchemy import text

        try:
            with self.engine.connect() as connection:
                connection.execute(text("SET LOCAL statement_timeout='3s'"))
                row = connection.execute(text("SELECT state,wait_event_type,wait_event,"
                    "cardinality(pg_blocking_pids(pid)) AS blockers,"
                    "(SELECT count(*) FROM pg_locks l WHERE l.pid=a.pid "
                    "AND l.mode='ShareLock') AS share_locks FROM pg_stat_activity a "
                    "WHERE pid=:pid"), {"pid":self.pid}).mappings().first()
                if row:
                    self.waits.append(dict(row))
            try:
                sample = cpu_sample(os.getpid())
                sample["client_cpu_seconds"] = sample.pop("backend_cpu_seconds")
                sample["backend_cpu_seconds"] = (
                    None if self.container else cpu_sample(self.pid)["backend_cpu_seconds"])
                self.cpu.append(sample)
            except (OSError, FileNotFoundError, ProcessLookupError):
                self.errors.append("BACKEND_CPU_UNAVAILABLE_CONTAINER_PID_NAMESPACE")
        except Exception as error:
            self.errors.append(type(error).__name__)

    def loop(self):
        while not self.stop.wait(0.5):
            self.sample()

    def __enter__(self):
        self.reader.writer_pid = self.pid
        self.reader.measuring = True
        self.reader.__enter__()
        self.sample()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=10)
        self.reader.finish()
        self.engine.dispose()
        if self.thread.is_alive():
            raise RuntimeError("A42_TELEMETRY_THREAD_DID_NOT_EXIT")

    def receipt(self):
        from scripts.publication_candidate_benchmark_v13 import distribution

        return {"writer_wait_samples":self.waits, "cpu_samples":self.cpu,
                "reader_latency":distribution(self.reader.latencies),
                "reader_errors":self.reader.errors, "sample_errors":self.errors,
                "scope":"backend PID CPU or unavailable across namespaces; host CPU whole machine; "
                "WAL/pg_stat_io are whole dedicated instance; cgroup is whole PG incl background"}
