"""Independent Reviewer read contract. No supervisor journal can instantiate it.

The baseline installation lacks a distinct Reviewer principal and approved FD
provisioning. Keep construction closed until a separately reviewed installer
supplies that identity; do not issue credentials or self-sign model evidence.
"""

from scripts.a42363_contract import require
from scripts.a42364_installation_verify import installed_package


class IndependentReviewSource:
    def __init__(self, package):
        p = installed_package(package)
        require("reviewer" in p.document.principals,
                "PUBLICATION_INDEPENDENT_REVIEWER_NOT_INSTALLED")
        require(False, "PUBLICATION_REVIEWER_KERNEL_CREDENTIAL_REQUIRED")

    def revalidate(self):
        require(False, "PUBLICATION_INDEPENDENT_REVIEWER_NOT_INSTALLED")

    def review(self, scope, binding):
        self.revalidate()
