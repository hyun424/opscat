"""P37 open-source configuration hardening.

Validates committed templates/manifests only. It never reads real `.env` files or
secret stores and keeps all runtime boundaries local/mock by default.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_SECRET_PATTERNS = (
    re.compile(r"sk_live_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"xoxb-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9_]{8,}"),
    re.compile(r"sntrys_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"nvapi-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"BEGIN PRIVATE KEY"),
    re.compile(r"actual-secret-value"),
)
_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "config_templates_only": True,
    "reads_real_env_files": False,
    "auth_session_work_enabled": False,
    "live_api_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class ConfigSurface:
    id: str
    path: str
    kind: str
    optional: bool
    required_flags: Mapping[str, Any]
    required_placeholders: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConfigSurface:
        flags = data.get("required_flags", {})
        return cls(
            id=str(data.get("id", "surface")),
            path=str(data.get("path", "")),
            kind=str(data.get("kind", "template")),
            optional=bool(data.get("optional", False)),
            required_flags=flags if isinstance(flags, Mapping) else {},
            required_placeholders=tuple(str(item) for item in _sequence(data.get("required_placeholders", ()))),
        )


@dataclass(frozen=True)
class ConfigSurfaceResult:
    surface: ConfigSurface
    exists: bool
    missing_placeholders: tuple[str, ...]
    real_secret_count: int
    unsafe_defaults: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def missing_placeholder_count(self) -> int:
        return len(self.missing_placeholders)

    @property
    def unsafe_default_count(self) -> int:
        return len(self.unsafe_defaults)

    @property
    def passed(self) -> bool:
        if not self.exists and not self.surface.optional:
            return False
        return self.real_secret_count == 0 and self.missing_placeholder_count == 0 and self.unsafe_default_count == 0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "surface_id": self.surface.id,
            "path": self.surface.path,
            "kind": self.surface.kind,
            "optional": self.surface.optional,
            "exists": self.exists,
            "passed": self.passed,
            "expected_placeholders": list(self.surface.required_placeholders),
            "missing_placeholders": list(self.missing_placeholders),
            "missing_placeholder_count": self.missing_placeholder_count,
            "real_secret_count": self.real_secret_count,
            "unsafe_defaults": list(self.unsafe_defaults),
            "unsafe_default_count": self.unsafe_default_count,
            "notes": list(self.notes),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class OpenSourceConfigHardeningReport:
    surfaces: tuple[ConfigSurfaceResult, ...]

    def to_dict(self) -> dict[str, Any]:
        total = len(self.surfaces)
        passed = sum(1 for surface in self.surfaces if surface.passed)
        secret_safe = sum(1 for surface in self.surfaces if surface.real_secret_count == 0)
        safe_defaults = sum(1 for surface in self.surfaces if surface.unsafe_default_count == 0)
        real_secret_count = sum(surface.real_secret_count for surface in self.surfaces)
        unsafe_default_count = sum(surface.unsafe_default_count for surface in self.surfaces)
        payload = {
            "summary": {
                "checked_surface_count": total,
                "passed_surface_count": passed,
                "blocker_count": real_secret_count + unsafe_default_count + sum(1 for surface in self.surfaces if not surface.exists and not surface.surface.optional),
                "passed": total >= 4 and passed == total and real_secret_count == 0 and unsafe_default_count == 0,
            },
            "score": {
                "template_pass_rate": _ratio(passed, total),
                "secret_safety_rate": _ratio(secret_safe, total),
                "safe_default_rate": _ratio(safe_defaults, total),
                "real_secret_count": real_secret_count,
                "unsafe_default_count": unsafe_default_count,
            },
            "boundary": dict(_BOUNDARY),
            "surfaces": [surface.to_dict() for surface in self.surfaces],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class OpenSourceConfigHardeningRunner:
    def run_path(self, path: str | Path) -> OpenSourceConfigHardeningReport:
        surfaces = load_config_surfaces(path)
        return OpenSourceConfigHardeningReport(surfaces=tuple(_evaluate_surface(surface) for surface in surfaces))


def load_config_surfaces(path: str | Path) -> tuple[ConfigSurface, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("surfaces", ()) if isinstance(data, Mapping) else ()
    return tuple(ConfigSurface.from_dict(item) for item in _sequence(raw) if isinstance(item, Mapping))


def run_open_source_config_hardening_fixture(path: str | Path) -> OpenSourceConfigHardeningReport:
    return OpenSourceConfigHardeningRunner().run_path(path)


def render_open_source_config_hardening_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Open-source Config Hardening Report",
        "",
        "Boundary: template validation only; no real .env reads; no auth/session implementation; no live API calls; no production mutation; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Checked surfaces: {summary.get('checked_surface_count')}",
        f"- Passed surfaces: {summary.get('passed_surface_count')}",
        f"- Blockers: {summary.get('blocker_count')}",
        "",
        "## Score",
        f"- Template pass rate: {score.get('template_pass_rate')}",
        f"- Secret safety rate: {score.get('secret_safety_rate')}",
        f"- Safe defaults: {score.get('safe_default_rate')}",
        f"- Real secret count: {score.get('real_secret_count')}",
        f"- Unsafe default count: {score.get('unsafe_default_count')}",
        "",
        "## Surfaces",
    ]
    for surface in _sequence(payload.get("surfaces", ())):
        if isinstance(surface, Mapping):
            lines.append(f"- `{surface.get('surface_id')}` kind={surface.get('kind')} passed={surface.get('passed')}")
    return "\n".join(lines) + "\n"


def write_open_source_config_hardening_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_open_source_config_hardening_markdown(payload), encoding="utf-8")


def _evaluate_surface(surface: ConfigSurface) -> ConfigSurfaceResult:
    path = Path(surface.path)
    if not path.exists():
        return ConfigSurfaceResult(
            surface=surface,
            exists=False,
            missing_placeholders=(),
            real_secret_count=0,
            unsafe_defaults=(),
            notes=("optional_missing" if surface.optional else "missing_required",),
        )
    text = path.read_text(encoding="utf-8")
    missing_placeholders = tuple(placeholder for placeholder in surface.required_placeholders if placeholder not in text)
    real_secret_count = _count_secret_markers(text)
    unsafe_defaults = _unsafe_defaults(text, surface.required_flags)
    notes = _notes_for(surface, text)
    return ConfigSurfaceResult(surface=surface, exists=True, missing_placeholders=missing_placeholders, real_secret_count=real_secret_count, unsafe_defaults=unsafe_defaults, notes=notes)


def _count_secret_markers(text: str) -> int:
    return sum(1 for pattern in _SECRET_PATTERNS for _ in pattern.finditer(text))


def _unsafe_defaults(text: str, required_flags: Mapping[str, Any]) -> tuple[str, ...]:
    if not required_flags:
        return ()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return tuple(required_flags)
    unsafe = []
    for key, expected in required_flags.items():
        if _lookup(data, str(key)) != expected:
            unsafe.append(str(key))
    return tuple(unsafe)


def _lookup(data: Any, dotted_key: str) -> Any:
    current = data
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _notes_for(surface: ConfigSurface, text: str) -> tuple[str, ...]:
    notes = []
    if surface.kind == "connector_manifest" and "credential_ref" in text:
        notes.append("credential_references_present")
    if surface.kind == "approval_profiles" and "auto_capabilities" in text:
        notes.append("approval_profiles_present")
    if surface.kind == "json_template":
        notes.append("json_template_checked")
    return tuple(notes)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)
