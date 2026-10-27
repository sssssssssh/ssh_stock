"""Fixed broker route. A journal lock is NOT a global storage exclusion proof.

The host MAC/namespace exclusion provider is deliberately unresolved: no root-owned
JSON, approved boolean or process census may turn it into a kernel capability.
The minimum broker is usable for refusal/status and records binding failures.
"""

import os
import re
from contextlib import contextmanager

from scripts.a42361_contract import canonical, sha
from scripts.a42362_contract import resources
from scripts.a42363_contract import require, scope_hash


class InstalledWriterBroker:
    def __init__(
        self,
        scope,
        authority,
        journal,
        graph_fd,
        run_fd,
        namespace_fd,
        runner,
        socket_directory=None,
        secret_fd=None,
        fixture_identity=None,
    ):
        require(journal.domain == "writer_broker", "BROKER_JOURNAL_REQUIRED")
        self.scope, self.authority, self.journal = scope, authority, journal
        self.fds = (graph_fd, run_fd, namespace_fd)
        self.identities = tuple(self._identity(fd) for fd in self.fds)
        self.runner = runner
        self.socket_directory, self.secret_fd, self.fixture_identity = (
            socket_directory,
            secret_fd,
            fixture_identity,
        )

    @staticmethod
    def _identity(fd):
        m = os.fstat(fd)
        return (m.st_dev, m.st_ino, m.st_mode, m.st_uid, m.st_gid)

    def verify_binding(self, scope):
        require(scope == self.scope, "BROKER_SCOPE_DRIFT")
        self.authority.require("SAFE_VOLUME_DISPOSAL")
        require(
            tuple(self._identity(fd) for fd in self.fds) == self.identities,
            "BROKER_STORE_OR_NAMESPACE_CHANGED",
        )
        return sha(
            canonical(dict(scope=scope_hash(scope), epoch=scope.epoch, identities=self.identities))
        )

    def verify_all_writers(self, scope, identity=None):
        self.verify_binding(scope)
        # This is an engineering gap, not an unsigned boolean waiting to be true.
        # SELinux/other MAC installation and hostile-writer proof are not supplied
        # by Podman's name-addressed rm API or by root ownership of this process.
        require(False, "ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY")

    @contextmanager
    def exclusive(self, scope, identity=None):
        self.verify_all_writers(scope, identity)
        # Unreachable until a reviewed kernel provider replaces the missing proof.
        # Retained interface allows KernelStoreCapability to use the same broker.
        yield self

    def dispatch(self, item, verb, original=None):
        require(
            item in resources(self.scope) and verb in ("create", "inspect", "start", "stop", "rm"),
            "BROKER_FIXED_OPERATION",
        )
        require(verb not in ("start", "stop") or item.kind == "CONTAINER", "BROKER_FIXED_OPERATION")
        self.verify_binding(item.scope)
        # All routes fail before runner; there is no inspect/create side channel.
        with self.exclusive(item.scope):
            require(original is not None or verb == "create", "BROKER_ORIGINAL_REQUIRED")
            require(self.runner is not None, "BROKER_INSTALLED_RUNNER_REQUIRED")
            event = "BROKER_" + item.kind + "_" + verb.upper()
            self.journal.append(
                self.scope,
                event + "_ATTEMPTED",
                dict(
                    original_sha256=None if original is None else sha(canonical(original)),
                    qualifies=False,
                ),
            )
            if item.kind == "SOCKET_DIR":
                require(
                    self.socket_directory is not None and verb in ("create", "inspect", "rm"),
                    "SOCKET_INSTALLED_ADAPTER_REQUIRED",
                )
                result = (
                    self.socket_directory.create(item)
                    if verb == "create"
                    else self.socket_directory.inspect(item)
                    if verb == "inspect"
                    else self.socket_directory.remove(item, original)
                )
            else:
                if verb != "create":
                    observed = self._inspect(item)
                    from scripts.a42363_resources import ResourceDriver

                    verifier = ResourceDriver(
                        None, self.socket_directory, self.secret_fd, None, self.fixture_identity
                    )
                    require(
                        verifier.verify(item, observed) == verifier.verify(item, original),
                        "VOLUME_ABA_OR_REPLACEMENT",
                    )
                    if item.kind == "VOLUME" and verb == "rm":
                        require(
                            observed.get("MountCount") == 0 and self._inspect(item) == observed,
                            "VOLUME_IN_USE_OR_FOREIGN",
                        )
                code, raw = self.runner.run(
                    self.command_plan(item, verb, original),
                    pass_fds=(self.secret_fd,)
                    if item.kind == "SECRET" and verb == "create"
                    else (),
                )
                require(code == 0 and len(raw) <= 32768, "BROKER_ACK_UNKNOWN_NO_RETRY")
                self.verify_binding(self.scope)
                result = (
                    self._inspect(item)
                    if verb in ("create", "inspect", "start", "stop")
                    else dict(removal_ack=True, independent_absence=False)
                )
            self.journal.append(self.scope, event + "_DONE", dict(result=result, qualifies=False))
            return result

    def _inspect(self, item):
        from scripts.a42361_contract import decode

        code, raw = self.runner.run(
            (item.kind.lower(), "inspect", "--format", "{{json .}}", item.name)
        )
        require(code == 0 and 0 < len(raw) <= 32768, "RESOURCE_INSPECT_UNKNOWN")
        return decode(raw)

    def command_plan(self, item, verb, original=None):
        require(
            item in resources(self.scope) and item.kind != "SOCKET_DIR", "BROKER_FIXED_OPERATION"
        )
        if verb == "create":
            from scripts.a42363_resources import ResourceDriver

            return ResourceDriver(
                None, self.socket_directory, self.secret_fd, None, self.fixture_identity
            ).creation_command(item)
        if verb == "inspect":
            return (item.kind.lower(), "inspect", "--format", "{{json .}}", item.name)
        require(
            verb in ("start", "stop", "rm") and type(original) is dict, "BROKER_FIXED_OPERATION"
        )
        if item.kind == "VOLUME":
            from scripts.a42364_volume_exclusion import volume_delete_plan

            require(verb == "rm" and original.get("Name") == item.name, "VOLUME_EXACT_NAME")
            return volume_delete_plan(item.name)["operation"]
        require(item.kind == "CONTAINER" or verb == "rm", "BROKER_FIXED_OPERATION")
        immutable = original.get("ID", original.get("Id"))
        require(
            type(immutable) is str
            and re.fullmatch(
                r"[0-9a-f]{64}" if item.kind == "CONTAINER" else r"(?:[0-9a-f]{25}|[0-9a-f]{64})",
                immutable,
            )
            is not None,
            "REMOVE_IMMUTABLE_ID_UNPROVEN",
        )
        return (item.kind.lower(), verb, immutable)

    def status(self):
        return dict(
            status="ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY",
            all_writer_proof=False,
            live_routes="DENY",
            name_addressed_volume_rm=True,
            qualifies=False,
            unresolved=[
                "unbypassable MAC policy for CLI/API/helper and same-UID writers",
                "rootless namespace and daemon restart lease revocation",
                "independent hostile-writer L2 proof",
            ],
        )
