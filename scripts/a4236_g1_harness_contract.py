"""A4236 pure contracts. No fixture/network/database/role creation implementation."""

import re


class Fault(RuntimeError):
    def __init__(self, code: str):
        self.code = code if re.fullmatch(r'A4236_[A-Z0-9_]{1,70}', code) else 'A4236_INTERNAL'
        super().__init__(self.code)


def require(condition, code):
    if not condition:
        raise Fault(code)
