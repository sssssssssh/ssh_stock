"""Linux-only owned harmless child tests; never self-provisions a sandbox.

No env bool enables this. The independently provisioned Linux lab must provide
an explicit in-process reviewed LabPermit to run the API; ordinary CI does not.
"""

import sys
import tempfile
import unittest
from pathlib import Path

from scripts import r1_integration_linux_domain as domain

# Only a separately approved in-process operator harness may supply a permit.
# The test never reads an env flag, creates a VM/container, or approves itself.
REVIEWED_LAB_PERMIT = None


class LinuxLabTests(unittest.TestCase):
    def test_AC37_environment_not_self_authorized(self):
        with self.assertRaises(domain.DomainError):
            domain.LinuxProcessDomain(None).spawn("no-permit", "success")

    def test_linux_success_term_kill_owned_child(self):
        if sys.platform != "linux" or REVIEWED_LAB_PERMIT is None:
            self.skipTest("NOT_RUN/ENV_BLOCKED: no independently approved no-network Linux lab")
        from scripts.r1_integration_durable_owner import DurableOwner

        for scenario in sorted(domain.SCENARIOS):
            with (
                self.subTest(scenario=scenario),
                tempfile.TemporaryDirectory(
                    dir=REVIEWED_LAB_PERMIT.private_directory,
                ) as directory,
            ):
                owner = DurableOwner(Path(directory))
                owner.reserve("synthetic-only")
                result = domain.run_lab_synthetic(
                    REVIEWED_LAB_PERMIT, owner, "synthetic-only", scenario
                )
                self.assertTrue(result["teardown"])
                self.assertTrue(result["durable_ack"])
                self.assertEqual(result["fencing"], "NOT_PROVEN")
                self.assertEqual(result["root"] == "SUCCESS", scenario == "success")
