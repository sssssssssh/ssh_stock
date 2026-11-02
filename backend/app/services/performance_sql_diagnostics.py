"""Bounded SQL event counters; no SQL, parameters or driver errors persisted."""

import hashlib
import re
from time import monotonic

from sqlalchemy import event

from app.services.performance_diagnostics import active_trace


def fingerprint(statement):
    """Only emit a digest; strip literals/comments including PostgreSQL dollar quotes."""
    pattern = r"--[^\n]*|/\*.*?\*/|\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$|'(?:''|[^'])*'|\b\d+(?:\.\d+)?\b"
    # Dollar quoting requires the same closing delimiter. Nested block comments
    # or nonstandard escaping are not parsed: return unavailable, never raw SQL.
    if "\\" in statement or statement.count("/*") > 1:
        return "unavailable"
    def replace(match):
        return "?" if not match[0].startswith(("--", "/*")) else " "
    for match in list(re.finditer(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", statement)):
        delimiter = match[0]
        if delimiter in statement:
            parts = statement.split(delimiter, 2)
            if len(parts) != 3:
                return "unavailable"
            statement = parts[0] + " ? " + parts[2]
    normalized = " ".join(re.sub(pattern, replace, statement, flags=re.S).split())
    return hashlib.sha256(normalized.encode()).hexdigest()


class SQLObserver:
    def __init__(self, engine, trace):
        self.engine, self.trace = engine, trace
        self.listeners = []
        self.fingerprints = {}

    def before(self, conn, cursor, statement, parameters, context, many):
        if active_trace.get() is not self.trace:
            return
        try:
            opaque = hashlib.sha256(statement.encode()).digest()
            key = self.fingerprints.get(opaque)
            if key is None:
                key = fingerprint(statement)
                if len(self.fingerprints) < 128:
                    self.fingerprints[opaque] = key
            if key not in self.trace.sql and len(self.trace.sql) >= 128:
                key = "overflow"
                self.trace.warnings.add("SQL_FINGERPRINT_LIMIT_REACHED")
            context.performance_diagnostic = (key, monotonic())
        except Exception:
            self.trace.warnings.add("SQL_OBSERVATION_UNAVAILABLE")

    def after(self, conn, cursor, statement, parameters, context, many):
        self.finish(context, cursor, False)

    def failed(self, error):
        self.finish(error.execution_context, None, True)

    def finish(self, context, cursor, failed):
        try:
            value = getattr(context, "performance_diagnostic", None)
            if value is None:
                return
            context.performance_diagnostic = None
            key, began = value
            elapsed = max(0, monotonic() - began) * 1000
            item = self.trace.sql.setdefault(key, dict(sql_fingerprint=key,
                fingerprint_kind="literal_stripped_statement_sha256",
                calls=0, total_ms=0.0, max_ms=0.0, average_ms=0.0,
                slow_calls=0, errors=0, affected_rows=None))
            item["calls"] += 1
            item["total_ms"] += elapsed
            item["max_ms"] = max(item["max_ms"], elapsed)
            item["average_ms"] = item["total_ms"] / item["calls"]
            item["slow_calls"] += int(elapsed >= 1000)
            item["errors"] += int(failed)
            count = getattr(cursor, "rowcount", -1)
            if count >= 0:
                item["affected_rows"] = (item["affected_rows"] or 0) + count
            self.trace.execute_calls += 1
        except Exception:
            self.trace.warnings.add("SQL_OBSERVATION_UNAVAILABLE")

    def install(self):
        for name, handler in (("before_cursor_execute", self.before),
                              ("after_cursor_execute", self.after), ("handle_error", self.failed)):
            event.listen(self.engine, name, handler)
            self.listeners.append((name, handler))

    def close(self):
        for name, handler in reversed(self.listeners):
            event.remove(self.engine, name, handler)
        self.listeners.clear()
        self.fingerprints.clear()
