"""Runtime authority sentinel for P107 local/mock prevention execution.

The sentinel is intentionally small and dependency-free: it records forbidden
authority attempts and raises immediately. P107 callers use the zero counter
shape as release evidence that no authority-bearing runtime path was touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AUTHORITY_COUNTER_KEYS = (
    "auth",
    "credential_reads",
    "production_adapter_calls",
    "production_mutation",
    "network_calls",
    "shell_calls",
    "cloud_calls",
    "db_mutation",
)

ZERO_AUTHORITY_COUNTERS = {key: 0 for key in AUTHORITY_COUNTER_KEYS}


class ForbiddenPreventionAuthority(RuntimeError):
    """Raised when P107 code attempts to cross the local/mock boundary."""


@dataclass
class PreventionAuthoritySentinel:
    counters: dict[str, int] = field(default_factory=lambda: dict(ZERO_AUTHORITY_COUNTERS))
    blocked: bool = False

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)

    def assert_zero_authority(self) -> bool:
        if any(value != 0 for value in self.counters.values()):
            raise ForbiddenPreventionAuthority("P107 authority boundary was breached")
        return True

    def record_auth_attempt(self, reason: str = "") -> None:
        self._block("auth", reason)

    def record_credential_read(self, reason: str = "") -> None:
        self._block("credential_reads", reason)

    def record_production_adapter_call(self, reason: str = "") -> None:
        self._block("production_adapter_calls", reason)

    def record_production_mutation(self, reason: str = "") -> None:
        self._block("production_mutation", reason)

    def record_shell_call(self, reason: str = "") -> None:
        self._block("shell_calls", reason)

    def record_network_call(self, reason: str = "") -> None:
        self._block("network_calls", reason)

    def record_cloud_mutation(self, reason: str = "") -> None:
        self._block("cloud_calls", reason)

    def record_db_mutation(self, reason: str = "") -> None:
        self._block("db_mutation", reason)

    def _block(self, key: str, reason: str) -> None:
        self.counters[key] = self.counters.get(key, 0) + 1
        self.blocked = True
        detail = f": {reason}" if reason else ""
        raise ForbiddenPreventionAuthority(f"P107 forbidden authority attempted for {key}{detail}")
