#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import math
import os
import re
import subprocess
import tarfile
import tomllib
import zipfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "evals" / "p122"
GENERATED_EVIDENCE_PREFIX = ("evals", "p122")
TEXT_SUFFIXES = {
    ".cfg",
    ".csv",
    ".env",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
CODE_CONFIG_SUFFIXES = {".py", ".sh", ".toml", ".yaml", ".yml", ".json"}
FIXTURE_PREFIXES = ("tests/", "evals/", "examples/", "docs/tickets/")
RISKY_LICENSE_TOKENS = ("AGPL", "GPL-2", "GPL-3")
ALLOWED_LICENSES = {
    "0BSD",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "MIT",
    "MPL-2.0",
    "PSF-2.0",
    "Python-2.0",
}
LICENSE_ALLOWLIST = {
    "annotated-doc": "MIT",
    "annotated-types": "MIT",
    "anyio": "MIT",
    "ast-serialize": "MIT",
    "certifi": "MPL-2.0",
    "click": "BSD-3-Clause",
    "colorama": "BSD-3-Clause",
    "distro": "Apache-2.0",
    "fastapi": "MIT",
    "greenlet": "MIT",
    "h11": "MIT",
    "httpcore": "BSD-3-Clause",
    "httptools": "MIT",
    "httpx": "BSD-3-Clause",
    "idna": "BSD-3-Clause",
    "iniconfig": "MIT",
    "jiter": "MIT",
    "librt": "MIT",
    "mypy": "MIT",
    "mypy-extensions": "MIT",
    "openai": "Apache-2.0",
    "opscat": "Apache-2.0",
    "packaging": "Apache-2.0 OR BSD-2-Clause",
    "pathspec": "MPL-2.0",
    "pluggy": "MIT",
    "psycopg": "LGPL-3.0-or-later",
    "psycopg-binary": "LGPL-3.0-or-later",
    "pydantic": "MIT",
    "pydantic-core": "MIT",
    "pydantic-settings": "MIT",
    "pygments": "BSD-2-Clause",
    "pytest": "MIT",
    "python-dotenv": "BSD-3-Clause",
    "pyyaml": "MIT",
    "ruff": "MIT",
    "sniffio": "Apache-2.0 OR MIT",
    "sqlalchemy": "MIT",
    "starlette": "BSD-3-Clause",
    "tqdm": "MPL-2.0 OR MIT",
    "typing-extensions": "PSF-2.0",
    "typing-inspection": "MIT",
    "tzdata": "Apache-2.0",
    "uvicorn": "BSD-3-Clause",
    "uvloop": "Apache-2.0 OR MIT",
    "watchfiles": "MIT",
    "websockets": "BSD-3-Clause",
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    path: str
    line: int
    message: str
    fingerprint: str

    def to_json(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "fingerprint": self.fingerprint,
        }


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("secret.aws_access_key_id", re.compile(r"\bA[KS]IA[0-9A-Z]{16}\b")),
    ("secret.github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")),
    ("secret.slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("secret.private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("secret.generic_assignment", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|credential)\b\s*[:=]\s*[\"']([^\"']{20,})[\"']")),
)
PRODUCTION_DEFAULT_PATTERN = re.compile(
    r"(?i)(?:prod|production|staging|kubernetes|kubectl|aws|gcp|azure|postgres(?:ql)?://|mysql://|redis://)"
)
DEFAULT_ASSIGNMENT_PATTERN = re.compile(r"(?i)^\s*[A-Z_]*(?:default|fallback|sample|demo|endpoint|url|host|target)[A-Z_]*\s*(?::[^=]+)?=")
NEGATED_PRODUCTION_CONTEXT = re.compile(r"(?i)\b(?:not|no|never|without|rather than|instead of|forbid|reject|block|fail closed)\b.{0,80}\b(?:prod|production|staging)\b")
SHELL_ACTION_PATTERN = re.compile(r"(?i)\b(?:incident|action|remediation|rollback|runbook|worker|approval)\b")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def inventory_hash(value: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps(list(value), sort_keys=True, separators=(",", ":"))
    return "sha256:" + sha256_text(canonical)


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def repo_visible_files(root: Path) -> list[Path]:
    git_dir = root / ".git"
    if git_dir.exists():
        result = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"], check=True, capture_output=True, text=True)
        candidates = [root / line for line in result.stdout.splitlines() if line]
    else:
        candidates = [path for path in root.rglob("*") if path.is_file()]
    return sorted(path for path in candidates if is_scannable_path(root, path))


def is_scannable_path(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    relative_posix = relative.as_posix()
    parts = set(relative.parts)
    if ".git" in parts or ".venv" in parts or "__pycache__" in parts:
        return False
    if relative.parts[:2] == GENERATED_EVIDENCE_PREFIX:
        return False
    if path.suffix not in TEXT_SUFFIXES:
        return False
    return path.is_file() and not relative_posix.endswith(".pyc")


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def build_source_inventory(root: Path, paths: Sequence[Path] | None = None) -> list[dict[str, Any]]:
    visible = repo_visible_files(root) if paths is None else list(paths)
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "hash": file_hash(path),
        }
        for path in visible
    ]


def build_archive_inventory(root: Path) -> list[dict[str, Any]]:
    dist = root / "dist"
    if not dist.is_dir():
        return []
    inventory: list[dict[str, Any]] = []
    for path in sorted(dist.glob("opscat-0.2.0*")):
        if path.suffix == ".whl":
            archive_format = "wheel"
            members, readable = _zip_member_inventory(path)
        elif path.name.endswith(".tar.gz"):
            archive_format = "sdist"
            members, readable = _tar_member_inventory(path)
        else:
            continue
        inventory.append(
            {
                "path": path.relative_to(root).as_posix(),
                "format": archive_format,
                "size": path.stat().st_size,
                "hash": file_hash(path),
                "readable": readable,
                "members": members,
            }
        )
    return inventory


def _zip_member_inventory(path: Path) -> tuple[list[dict[str, Any]], bool]:
    try:
        with zipfile.ZipFile(path) as archive:
            return [
                {"path": info.filename.replace("\\", "/"), "size": info.file_size, "hash": "sha256:" + hashlib.sha256(archive.read(info)).hexdigest()}
                for info in sorted((item for item in archive.infolist() if not item.is_dir()), key=lambda item: item.filename)
            ], True
    except (OSError, RuntimeError, zipfile.BadZipFile):
        return [], False


def _tar_member_inventory(path: Path) -> tuple[list[dict[str, Any]], bool]:
    try:
        with tarfile.open(path, "r:gz") as archive:
            members: list[dict[str, Any]] = []
            for member in sorted((item for item in archive.getmembers() if item.isfile()), key=lambda item: item.name):
                extracted = archive.extractfile(member)
                if extracted is None:
                    return [], False
                content = extracted.read()
                members.append({"path": member.name.replace("\\", "/"), "size": member.size, "hash": "sha256:" + hashlib.sha256(content).hexdigest()})
            return members, True
    except (OSError, tarfile.TarError):
        return [], False


def entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def fingerprint(path: str, line: int, rule_id: str, match_text: str) -> str:
    return sha256_text(f"{path}:{line}:{rule_id}:{match_text}")[:16]


def line_finding(rule_id: str, severity: str, relative: Path, line_no: int, message: str, match_text: str) -> Finding:
    path = relative.as_posix()
    return Finding(rule_id=rule_id, severity=severity, path=path, line=line_no, message=message, fingerprint=fingerprint(path, line_no, rule_id, match_text))


def scan_secrets(root: Path, paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        relative = path.relative_to(root)
        for line_no, line in enumerate(text.splitlines(), start=1):
            for rule_id, pattern in SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    secret_value = match.group(1) if rule_id == "secret.generic_assignment" and match.groups() else match.group(0)
                    if rule_id == "secret.generic_assignment" and (entropy(secret_value) < 3.5 or secret_value.startswith(("example", "redacted", "changeme"))):
                        continue
                    findings.append(line_finding(rule_id, "critical", relative, line_no, "Potential secret material detected; value redacted.", secret_value))
    return findings


def is_fixture_or_documentation(relative: Path) -> bool:
    relative_posix = relative.as_posix()
    return relative_posix.startswith(FIXTURE_PREFIXES)


def scan_mutable_production_defaults(root: Path, paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        relative = path.relative_to(root)
        if path.suffix not in CODE_CONFIG_SUFFIXES or is_fixture_or_documentation(relative):
            continue
        text = read_text(path)
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "re.compile" in line or line.strip().startswith(('r"', "r'")):
                continue
            right_hand_side = line.split("=", 1)[1] if "=" in line else ""
            literal_rhs = re.search(r"[\"'][^\"']+[\"']", right_hand_side) is not None
            if DEFAULT_ASSIGNMENT_PATTERN.search(line) and literal_rhs and PRODUCTION_DEFAULT_PATTERN.search(right_hand_side) and not NEGATED_PRODUCTION_CONTEXT.search(line):
                findings.append(line_finding("default.production_like_mutable_target", "high", relative, line_no, "Production-like or staging-like endpoint appears in a default/config path.", line))
    return findings


def scan_shell_incident_paths(root: Path, paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        relative = path.relative_to(root)
        if path.suffix != ".py" or is_fixture_or_documentation(relative):
            continue
        text = read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=relative.as_posix())
        except SyntaxError as exc:
            findings.append(
                Finding(
                    rule_id="static.python_parse_error",
                    severity="high",
                    path=relative.as_posix(),
                    line=exc.lineno or 1,
                    message="Python source could not be parsed for security gate checks.",
                    fingerprint=fingerprint(relative.as_posix(), exc.lineno or 1, "static.python_parse_error", exc.msg),
                )
            )
            continue
        findings.extend(_scan_ast_for_shell_actions(relative, tree))
    return findings


def _name_of_call(node: ast.Call) -> str:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        parts = [function.attr]
        value = function.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _constant_string(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _scan_ast_for_shell_actions(relative: Path, tree: ast.AST, *, scope_relative: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    scan_scope = scope_relative or relative
    scope_stack: list[str] = [scan_scope.as_posix()]
    risky_calls = {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output", "os.system", "os.popen"}

    class Visitor(ast.NodeVisitor):
        def _visit_scoped_node(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
            scope_stack.append(node.name)
            self.generic_visit(node)
            scope_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._visit_scoped_node(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._visit_scoped_node(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            self._visit_scoped_node(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            call_name = _name_of_call(node)
            joined_scope = ".".join(scope_stack)
            first_arg = _constant_string(node.args[0]) if node.args else ""
            shell_true = any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords)
            incident_context = SHELL_ACTION_PATTERN.search(joined_scope) is not None or SHELL_ACTION_PATTERN.search(first_arg) is not None
            arbitrary_command = call_name in risky_calls and _is_arbitrary_command_arg(node)
            if arbitrary_command and _arbitrary_subprocess_path_in_scope(scan_scope):
                findings.append(
                    Finding(
                        rule_id="static.arbitrary_subprocess_execution",
                        severity="high",
                        path=relative.as_posix(),
                        line=node.lineno,
                        message="Arbitrary subprocess execution is reachable from a non-literal command argument.",
                        fingerprint=fingerprint(relative.as_posix(), node.lineno, "static.arbitrary_subprocess_execution", f"{call_name}:{joined_scope}"),
                    )
                )
            if call_name in risky_calls and (shell_true or incident_context):
                findings.append(
                    Finding(
                        rule_id="static.shell_subprocess_incident_action",
                        severity="critical" if shell_true else "high",
                        path=relative.as_posix(),
                        line=node.lineno,
                        message="Shell/subprocess execution is reachable from an incident/action-like path.",
                        fingerprint=fingerprint(relative.as_posix(), node.lineno, "static.shell_subprocess_incident_action", f"{call_name}:{joined_scope}:{first_arg}:{shell_true}"),
                    )
                )
            self.generic_visit(node)

    Visitor().visit(tree)
    return findings


def _is_arbitrary_command_arg(node: ast.Call) -> bool:
    if not node.args:
        return False
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return False
    if isinstance(first, (ast.List, ast.Tuple)):
        return False
    return True


def _arbitrary_subprocess_path_in_scope(relative: Path) -> bool:
    parts = relative.parts
    if not parts:
        return False
    if parts[0] == "scripts":
        return relative.name.startswith(("run_p122_", "verify_p122_", "build_p122_", "validate_p122_"))
    return parts[0] == "app" or len(parts) == 1


def scan_distribution_artifacts(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    dist = root / "dist"
    if not dist.is_dir():
        return findings
    for path in sorted(dist.glob("opscat-0.2.0*")):
        if path.suffix == ".whl":
            findings.extend(_scan_zip_artifact(path))
        elif path.name.endswith(".tar.gz"):
            findings.extend(_scan_tar_artifact(path))
    return findings


def _scan_zip_artifact(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                normalized = _normalized_archive_app_path(name)
                if normalized is not None and normalized.suffix == ".py":
                    findings.extend(_scan_artifact_python_member(path.name, normalized, archive.read(name).decode("utf-8")))
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile):
        findings.append(line_finding("artifact.unreadable_package", "high", Path("dist") / path.name, 1, "Generated wheel could not be scanned.", path.name))
    return findings


def _scan_tar_artifact(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        with tarfile.open(path, "r:gz") as archive:
            for member in sorted((item for item in archive.getmembers() if item.isfile()), key=lambda item: item.name):
                normalized = _normalized_archive_app_path(member.name)
                if normalized is not None and normalized.suffix == ".py":
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        findings.extend(_scan_artifact_python_member(path.name, normalized, extracted.read().decode("utf-8")))
    except (OSError, UnicodeDecodeError, tarfile.TarError):
        findings.append(line_finding("artifact.unreadable_package", "high", Path("dist") / path.name, 1, "Generated sdist could not be scanned.", path.name))
    return findings


def _normalized_archive_app_path(member_name: str) -> Path | None:
    parts = tuple(part for part in member_name.replace("\\", "/").split("/") if part not in {"", "."})
    if ".." in parts or "app" not in parts:
        return None
    app_index = parts.index("app")
    normalized = Path(*parts[app_index:])
    return normalized if len(normalized.parts) > 1 else None


def _scan_artifact_python_member(artifact_name: str, member_name: Path, text: str) -> list[Finding]:
    relative = Path("dist") / f"{artifact_name}!{member_name.as_posix()}"
    try:
        tree = ast.parse(text, filename=relative.as_posix())
    except SyntaxError as exc:
        return [
            Finding(
                rule_id="artifact.python_parse_error",
                severity="high",
                path=relative.as_posix(),
                line=exc.lineno or 1,
                message="Packaged Python source could not be parsed for security gate checks.",
                fingerprint=fingerprint(relative.as_posix(), exc.lineno or 1, "artifact.python_parse_error", exc.msg),
            )
        ]
    return _scan_ast_for_shell_actions(relative, tree, scope_relative=member_name)


def parse_uv_lock(lock_path: Path) -> list[dict[str, Any]]:
    lock = tomllib.loads(lock_path.read_text())
    packages = lock.get("package", [])
    if not isinstance(packages, list):
        raise ValueError("uv.lock package table is missing or malformed")
    return [package for package in packages if isinstance(package, dict) and package.get("name") and package.get("version")]


def hashes_for_package(package: Mapping[str, Any]) -> list[dict[str, str]]:
    hashes: list[dict[str, str]] = []
    for artifact_key in ("sdist",):
        artifact = package.get(artifact_key)
        if isinstance(artifact, Mapping) and isinstance(artifact.get("hash"), str):
            algorithm, _, content = artifact["hash"].partition(":")
            if algorithm and content:
                hashes.append({"alg": algorithm.upper(), "content": content})
    wheels = package.get("wheels")
    if isinstance(wheels, list):
        for wheel in wheels:
            if isinstance(wheel, Mapping) and isinstance(wheel.get("hash"), str):
                algorithm, _, content = wheel["hash"].partition(":")
                if algorithm and content:
                    hashes.append({"alg": algorithm.upper(), "content": content})
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for item in hashes:
        unique[(item["alg"], item["content"])] = item
    return list(unique.values())


def build_sbom(packages: Sequence[Mapping[str, Any]], root: Path) -> dict[str, Any]:
    lock_hash = sha256_text((root / "uv.lock").read_text()) if (root / "uv.lock").exists() else ""
    components = []
    for package in sorted(packages, key=lambda item: str(item["name"]).lower()):
        name = str(package["name"])
        version = str(package["version"])
        hashes = hashes_for_package(package)
        components.append(
            {
                "type": "library",
                "bom-ref": f"pkg:pypi/{name}@{version}",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name}@{version}",
                "hashes": hashes,
                "evidence": {"source": "uv.lock", "hashes_present": bool(hashes)},
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{sha256_text(lock_hash)[:32]}",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "opscat", "version": "0.2.0"},
            "properties": [{"name": "opscat:p122:uv_lock_sha256", "value": lock_hash}],
        },
        "components": components,
    }


def normalize_license(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value or value.upper() in {"UNKNOWN", "UNKNOWN LICENSE"}:
        return None
    replacements = {
        "Apache Software License": "Apache-2.0",
        "BSD License": "BSD-3-Clause",
        "MIT License": "MIT",
        "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
        "PSFL": "PSF-2.0",
    }
    return replacements.get(value, value)


def installed_license_for(name: str) -> str | None:
    try:
        metadata = importlib.metadata.metadata(name)
    except importlib.metadata.PackageNotFoundError:
        return None
    expression = normalize_license(metadata.get("License-Expression"))
    if expression:
        return expression
    classifiers = metadata.get_all("Classifier") or []
    for classifier in classifiers:
        if "License :: OSI Approved :: Apache Software License" in classifier:
            return "Apache-2.0"
        if "License :: OSI Approved :: MIT License" in classifier:
            return "MIT"
        if "License :: OSI Approved :: BSD License" in classifier:
            return "BSD-3-Clause"
        if "License :: OSI Approved :: Mozilla Public License 2.0" in classifier:
            return "MPL-2.0"
    return normalize_license(metadata.get("License"))


def license_status(expression: str | None) -> str:
    if expression is None:
        return "unknown"
    if re.search(r"\b(?:AGPL|GPL)-(?:2|3)", expression.upper()):
        return "incompatible"
    tokens = {token.strip("() ") for token in re.split(r"\s+(?:OR|AND)\s+", expression) if token.strip("() ")}
    if tokens and tokens.issubset(ALLOWED_LICENSES):
        return "allowed"
    return "unknown"


def build_license_inventory(packages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for package in sorted(packages, key=lambda item: str(item["name"]).lower()):
        name = str(package["name"])
        license_expression = installed_license_for(name) or LICENSE_ALLOWLIST.get(name)
        status = license_status(license_expression)
        entry = {"name": name, "version": str(package["version"]), "license": license_expression, "status": status}
        entries.append(entry)
        if status != "allowed":
            findings.append(
                {
                    "rule_id": f"license.{status}",
                    "severity": "high",
                    "package": name,
                    "version": str(package["version"]),
                    "license": license_expression,
                    "message": "Dependency license is unknown or incompatible for the P122 release gate.",
                }
            )
    return {
        "policy": {"allowed": sorted(ALLOWED_LICENSES), "incompatible_tokens": list(RISKY_LICENSE_TOKENS)},
        "components": entries,
        "findings": findings,
    }


def build_security_report(root: Path, output_dir: Path) -> dict[str, Any]:
    root = root.resolve()
    paths = repo_visible_files(root)
    source_inventory = build_source_inventory(root, paths)
    archive_inventory = build_archive_inventory(root)
    source_inventory_digest = inventory_hash(source_inventory)
    archive_inventory_digest = inventory_hash(archive_inventory)
    packages = parse_uv_lock(root / "uv.lock")
    artifact_findings = scan_distribution_artifacts(root)
    findings = scan_secrets(root, paths) + scan_mutable_production_defaults(root, paths) + scan_shell_incident_paths(root, paths) + artifact_findings
    sbom = build_sbom(packages, root)
    license_inventory = build_license_inventory(packages)
    for license_finding in license_inventory["findings"]:
        findings.append(
            Finding(
                rule_id=str(license_finding["rule_id"]),
                severity=str(license_finding["severity"]),
                path="uv.lock",
                line=1,
                message=str(license_finding["message"]),
                fingerprint=fingerprint("uv.lock", 1, str(license_finding["rule_id"]), f"{license_finding['package']}:{license_finding['version']}:{license_finding['license']}"),
            )
        )
    severity_counts = Counter(finding.severity for finding in findings)
    blocking = [finding for finding in findings if finding.severity in {"critical", "high"}]
    report = {
        "schema_version": "p122.security_report.v2",
        "gate": "p122_security_supply_chain",
        "status": "fail" if blocking else "pass",
        "root": str(root),
        "root_binding_hash": "sha256:"
        + sha256_text(
            json.dumps(
                {
                    "root": str(root),
                    "source_inventory_hash": source_inventory_digest,
                    "archive_inventory_hash": archive_inventory_digest,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        "source_inventory": source_inventory,
        "source_inventory_hash": source_inventory_digest,
        "archive_inventory": archive_inventory,
        "archive_inventory_hash": archive_inventory_digest,
        "scanned_file_count": len(source_inventory),
        "dependency_count": len(packages),
        "generated_artifact_scan_count": len(archive_inventory),
        "severity_counts": dict(sorted(severity_counts.items())),
        "findings": [finding.to_json() for finding in sorted(findings, key=lambda item: (item.severity, item.rule_id, item.path, item.line, item.fingerprint))],
        "artifacts": {
            "security_report": str((output_dir / "security-report.json").relative_to(root)),
            "sbom": str((output_dir / "sbom.json").relative_to(root)),
            "license_inventory": str((output_dir / "license-inventory.json").relative_to(root)),
        },
        "limitations": [
            "This deterministic static gate performs no network lookup; scripts/run_p122_vulnerability_audit.py provides a separate freshness-bound advisory database gate.",
            "Secret scanning is regex and entropy based; it can miss novel token formats and intentionally redacts matched values.",
            "Static shell/action checks are heuristic and focus on Python subprocess/os.system paths in non-fixture source.",
            "License metadata prefers installed package metadata and falls back to the documented in-script allowlist.",
        ],
    }
    report["report_hash"] = "sha256:" + sha256_text(json.dumps({key: value for key, value in report.items() if key != "report_hash"}, sort_keys=True, separators=(",", ":")))
    write_json_atomic(output_dir / "sbom.json", sbom)
    write_json_atomic(output_dir / "license-inventory.json", license_inventory)
    write_json_atomic(output_dir / "security-report.json", report)
    return report


def security_report_current(report: Mapping[str, Any], *, root: Path) -> bool:
    try:
        resolved_root = root.resolve()
        paths = repo_visible_files(resolved_root)
        source_inventory = build_source_inventory(resolved_root, paths)
        archive_inventory = build_archive_inventory(resolved_root)
        source_digest = inventory_hash(source_inventory)
        archive_digest = inventory_hash(archive_inventory)
        root_binding_hash = "sha256:" + sha256_text(
            json.dumps(
                {"root": str(resolved_root), "source_inventory_hash": source_digest, "archive_inventory_hash": archive_digest},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        findings = (
            scan_secrets(resolved_root, paths)
            + scan_mutable_production_defaults(resolved_root, paths)
            + scan_shell_incident_paths(resolved_root, paths)
            + scan_distribution_artifacts(resolved_root)
        )
        expected_findings = [
            finding.to_json()
            for finding in sorted(findings, key=lambda item: (item.severity, item.rule_id, item.path, item.line, item.fingerprint))
        ]
        expected_severities = dict(sorted(Counter(finding.severity for finding in findings).items()))
        payload = {key: value for key, value in report.items() if key != "report_hash"}
        expected_hash = "sha256:" + sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return (
            report.get("schema_version") == "p122.security_report.v2"
            and report.get("root") == str(resolved_root)
            and report.get("root_binding_hash") == root_binding_hash
            and report.get("source_inventory") == source_inventory
            and report.get("source_inventory_hash") == source_digest
            and report.get("archive_inventory") == archive_inventory
            and report.get("archive_inventory_hash") == archive_digest
            and report.get("scanned_file_count") == len(source_inventory)
            and report.get("generated_artifact_scan_count") == len(archive_inventory)
            and report.get("dependency_count") == len(parse_uv_lock(resolved_root / "uv.lock"))
            and report.get("findings") == expected_findings
            and report.get("severity_counts") == expected_severities
            and report.get("status") == ("fail" if any(finding.severity in {"critical", "high"} for finding in findings) else "pass")
            and report.get("report_hash") == expected_hash
        )
    except (OSError, subprocess.SubprocessError, tarfile.TarError, tomllib.TOMLDecodeError, zipfile.BadZipFile):
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic P122 security and supply-chain release gate.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-fail", action="store_true", help="Write artifacts but exit zero even when blocking findings exist.")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    report = build_security_report(root, output_dir)
    print(
        json.dumps(
            {
                "gate": report["gate"],
                "status": report["status"],
                "scanned_file_count": report["scanned_file_count"],
                "dependency_count": report["dependency_count"],
                "severity_counts": report["severity_counts"],
                "findings_redacted": True,
            },
            sort_keys=True,
        )
    )
    return 0 if args.no_fail or report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
