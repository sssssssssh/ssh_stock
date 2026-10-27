import app.services.calculation_memory as memory
import pytest


def test_available_headroom_fails_before_next_allocation(monkeypatch):
    monkeypatch.setattr(memory, "process_memory_bytes", lambda: (100, 200))
    monkeypatch.setattr(memory, "available_memory_bytes", lambda: 1024)
    with pytest.raises(MemoryError, match="AVAILABLE_MEMORY"):
        memory.check_calculation_memory(reserve=2048)


def test_rss_guard_is_independent_of_available_host_memory(monkeypatch):
    monkeypatch.setattr(memory, "process_memory_bytes", lambda: (300, 400))
    monkeypatch.setattr(memory, "available_memory_bytes", lambda: 10**12)
    with pytest.raises(MemoryError, match="PROCESS_MEMORY"):
        memory.check_calculation_memory(limit=299)


def test_unobservable_memory_is_not_silently_treated_as_unlimited(monkeypatch):
    def unavailable():
        raise OSError("PRIVATE_OBSERVATION_DETAILS")

    monkeypatch.setattr(memory, "process_memory_bytes", unavailable)
    with pytest.raises(RuntimeError, match="^CALCULATION_MEMORY_OBSERVATION_FAILED$"):
        memory.check_calculation_memory()
