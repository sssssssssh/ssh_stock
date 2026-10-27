"""Process memory observation without a third-party dependency."""

import sys
from pathlib import Path


def process_memory_bytes():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "peak", "working", "peak_paged", "paged", "peak_nonpaged",
                    "nonpaged", "pagefile", "peak_pagefile",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ]
        value = Counters()
        value.cb = ctypes.sizeof(value)
        observed = psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(value), value.cb)
        if not observed:
            raise RuntimeError("CALCULATION_MEMORY_OBSERVATION_FAILED")
        return value.working, value.peak
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak *= 1 if sys.platform == "darwin" else 1024
    if sys.platform.startswith("linux"):
        for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
            parts = line.split()
            if parts and parts[0] == "VmRSS:" and len(parts) == 3 and parts[2] == "kB":
                return int(parts[1]) * 1024, peak
        raise RuntimeError("CALCULATION_MEMORY_OBSERVATION_FAILED")
    return peak, peak  # Other POSIX peak is conservative, not current RSS.


def available_memory_bytes():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Status(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
                (name, ctypes.c_ulonglong) for name in (
                    "total", "available", "total_page", "available_page", "total_virtual",
                    "available_virtual", "extended",
                )
            ]

        status = Status()
        status.length = ctypes.sizeof(status)
        if not ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(status)):
            raise RuntimeError("CALCULATION_MEMORY_OBSERVATION_FAILED")
        return status.available
    if sys.platform.startswith("linux"):
        available = None
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            parts = line.split()
            if parts and parts[0] == "MemAvailable:" and parts[-1] == "kB":
                available = int(parts[1]) * 1024
                break
        if available is None:
            raise RuntimeError("CALCULATION_MEMORY_OBSERVATION_FAILED")
        # Standard container cgroup-v2 cap, read only; no controller/probe writes.
        maximum = Path("/sys/fs/cgroup/memory.max")
        current = Path("/sys/fs/cgroup/memory.current")
        if maximum.is_file() and current.is_file():
            cap = maximum.read_text(encoding="ascii").strip()
            if cap != "max":
                available = min(available, max(0, int(cap) - int(current.read_text())))
        else:
            maximum = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            current = Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
            if maximum.is_file() and current.is_file():
                remaining = int(maximum.read_text()) - int(current.read_text())
                available = min(available, max(0, remaining))
        return available
    raise RuntimeError("CALCULATION_MEMORY_OBSERVATION_FAILED")


def check_calculation_memory(limit=3 * 1024**3, *, reserve=256 * 1024**2):
    try:
        current, peak = process_memory_bytes()
        available = available_memory_bytes()
    except (OSError, ValueError, ImportError):
        raise RuntimeError("CALCULATION_MEMORY_OBSERVATION_FAILED") from None
    if current >= limit:
        raise MemoryError("CALCULATION_PROCESS_MEMORY_BUDGET_EXCEEDED")
    if available <= reserve:
        raise MemoryError("CALCULATION_AVAILABLE_MEMORY_BUDGET_EXCEEDED")
    return current, peak
