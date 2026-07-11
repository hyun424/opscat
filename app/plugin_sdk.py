"""Minimal stable read-only connector interface for third-party fixtures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable


class MutationDenied(PermissionError):
    """Raised when a connector attempts to expose mutation authority."""


@runtime_checkable
class ReadOnlyConnectorV1(Protocol):
    connector_id: str

    def collect(self, query: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]: ...


def validate_read_only_connector(connector: ReadOnlyConnectorV1) -> None:
    if not isinstance(connector, ReadOnlyConnectorV1) or not connector.connector_id.strip():
        raise TypeError("invalid_read_only_connector_v1")
    forbidden = {"write", "mutate", "execute", "delete", "apply", "patch"}
    exposed = forbidden & set(dir(connector))
    if exposed:
        raise MutationDenied(f"mutation_capability_denied:{sorted(exposed)[0]}")


__all__ = ["MutationDenied", "ReadOnlyConnectorV1", "validate_read_only_connector"]
