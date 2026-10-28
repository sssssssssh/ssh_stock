"""Durable four-resource lifecycle; unknown ACKs never authorize a second action."""

import time

from scripts.a42361_contract import canonical, sha
from scripts.a42362_contract import resources
from scripts.a42363_contract import require
from scripts.a42365_contract import safe_code


class ResourceLifecycle:
    def __init__(self, scope, journal, driver):
        require(journal.domain == "controller", "CONTROLLER_JOURNAL_REQUIRED")
        self.scope, self.journal, self.driver = scope, journal, driver

    def _key(self, item, verb):
        require(item in resources(self.scope), "RESOURCE_SCOPE")
        require(verb in ("CREATE", "INSPECT", "START", "STOP", "REMOVE"), "RESOURCE_VERB")
        return item.kind + "_" + verb

    def original(self, item):
        return self.journal.read(self.scope, item.kind + "_ORIGINAL").record

    def _inspect_original(self, item):
        original = self.original(item)
        current = self.driver.inspect(item)
        require(
            self.driver.verify(item, current) == original["identity_sha256"],
            "OWNERSHIP_UNKNOWN_QUARANTINE",
        )
        return current

    def perform(self, item, verb):
        key = self._key(item, verb)
        try:
            if verb in ("START", "STOP"):
                require(item.kind == "CONTAINER", "RESOURCE_VERB")
            require(
                self.journal.maybe_read(self.scope, key + "_ATTEMPTED") is None,
                "RESOURCE_ACK_UNKNOWN_NO_REPLAY",
            )
            original_record = None if verb == "CREATE" else self.original(item)
            self.journal.append(
                self.scope,
                key + "_ATTEMPTED",
                dict(
                    original_sha256=None
                    if original_record is None
                    else original_record["identity_sha256"],
                    attempted_ns=time.monotonic_ns(),
                    qualifies=False,
                ),
            )
            original = None if verb == "CREATE" else self._inspect_original(item)
            if verb == "CREATE":
                raw = self.driver.create(item)
                identity = self.driver.verify(item, raw)
                # This append is unique and never replaced by a later inspection.
                self.journal.append(
                    self.scope,
                    item.kind + "_ORIGINAL",
                    dict(
                        raw=raw,
                        identity_sha256=identity,
                        raw_sha256=sha(canonical(raw)),
                        qualifies=False,
                    ),
                )
            elif verb == "INSPECT":
                raw = original
            elif verb == "REMOVE":
                self.driver.remove(item, original)
                raw = dict(removal_ack=True)  # Not absence; only E can attest that.
            else:
                getattr(self.driver, verb.lower())(item, original)
                raw = self._inspect_original(item)
            return self.journal.append(self.scope, key + "_DONE", dict(raw=raw, qualifies=False))
        except BaseException as error:
            try:
                self.record_error(safe_code(error), key)
            except BaseException:
                error.cleanup_codes = [
                    *getattr(error, "cleanup_codes", []),
                    "A42363_FIRST_ERROR_JOURNAL_UNKNOWN",
                ]
            raise

    def record_error(self, code, operation):
        if self.journal.maybe_read(self.scope, "FIRST_ERROR") is None:
            try:
                self.journal.append(self.scope, "FIRST_ERROR", dict(code=code, operation=operation))
            except Exception:
                # A competing committed first error is preserved. No resource operation here.
                require(
                    self.journal.maybe_read(self.scope, "FIRST_ERROR") is not None,
                    "FIRST_ERROR_ACK_UNKNOWN",
                )
        event = "CLEANUP_" + sha((operation + ":" + code).encode())[:32]
        if self.journal.maybe_read(self.scope, event) is None:
            self.journal.append(self.scope, event, dict(code=code, operation=operation))

    def recover(self):
        cleanup = []
        for item in reversed(resources(self.scope)):
            created = self.journal.maybe_read(self.scope, item.kind + "_ORIGINAL")
            attempted = self.journal.maybe_read(self.scope, item.kind + "_CREATE_ATTEMPTED")
            if not created:
                if attempted:
                    cleanup.append(item.kind + "_CREATE_ACK_UNKNOWN")
                continue  # Unknown creation is never adopted or removed by name.
            if self.journal.maybe_read(self.scope, item.kind + "_CREATE_DONE") is None:
                cleanup.append(item.kind + "_CREATE_ACK_UNKNOWN")
                continue
            removed = self.journal.maybe_read(self.scope, item.kind + "_REMOVE_DONE")
            if removed:
                continue
            try:
                if item.kind == "CONTAINER":
                    started = self.journal.maybe_read(self.scope, "CONTAINER_START_ATTEMPTED")
                    stopped = self.journal.maybe_read(self.scope, "CONTAINER_STOP_DONE")
                    if started and not stopped:
                        if self.journal.maybe_read(self.scope, "CONTAINER_START_DONE") is None:
                            cleanup.append("CONTAINER_START_ACK_UNKNOWN")
                            continue
                        self.perform(item, "STOP")
                self.perform(item, "REMOVE")
            except Exception as error:
                cleanup.append(safe_code(error))
        return dict(
            status="INCOMPLETE_QUARANTINED" if cleanup else "DESTROYED_PENDING_INDEPENDENT_E",
            cleanup_codes=cleanup,
            first_error=(
                self.journal.maybe_read(self.scope, "FIRST_ERROR").record
                if self.journal.maybe_read(self.scope, "FIRST_ERROR")
                else None
            ),
            qualifies=False,
        )
