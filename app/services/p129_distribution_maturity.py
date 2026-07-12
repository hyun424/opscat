"""P129 OSS distribution maturity evidence aggregation."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import shutil
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.public_contracts import public_contract_manifest
from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters

P129_DISTRIBUTION_SCHEMA_VERSION = "p129.distribution_report.v1"
P129_RELEASE_SCHEMA_VERSION = "p129.release_evidence.v1"
_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_GOVERNED_DOCS = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/installation.md",
    "docs/compatibility.md",
    "docs/limitations.md",
)
_P129_PLANNING_DOCS = (
    "docs/operations/p129-oss-distribution-maturity-roadmap.md",
    "docs/operations/p129-test-spec.md",
    "docs/operations/p129-plan-review.md",
    "docs/operations/p129-verification-handoff.md",
    "docs/tickets/p129/README.md",
)
_DOC_REQUIRED_TERMS = {
    "README.md": ("Public limitation", "local/mock/sandbox", "no secrets"),
    "SECURITY.md": ("private vulnerability", "Do not submit secrets", "production credentials"),
    "CONTRIBUTING.md": ("Capability claims must link", "P122 security", "production autonomy"),
    "docs/installation.md": ("Python 3.12", "Python 3.13", "Python 3.14", "uv sync --frozen", "no credentials"),
    "docs/compatibility.md": ("deprecation", "migration", "stable-v1", "Python 3.12", "Python 3.13", "Python 3.14"),
    "docs/limitations.md": ("local/mock/sandbox", "credentialed execution", "production or staging mutation"),
}
_PYTHON_VERSIONS = ("3.12", "3.13", "3.14")
_PROHIBITED_CLAIMS = re.compile(r"\b(?:production-ready|production-readiness|enterprise support|fully autonomous|operator replacement complete)\b", re.IGNORECASE)
_CLAIM_LIMITERS = (
    r"\bnot\b",
    r"\bno\b",
    r"\bdoes not\b",
    r"\bdo not\b",
    r"\bmay not\b",
    r"\bmust not\b",
    r"\bforbid(?:s|den)?\b",
    r"\bforbidden\b",
    r"\bout of scope\b",
    r"\buntil\b",
    r"\breject(?:s|ed|ing)?\b",
    r"\bblock(?:s|ed|ing)?\b",
    r"\brequired rejections?\b",
    r"\bstop conditions?\b",
    r"\bstop on\b",
    r"\bblock handoff on\b",
)
_CLAIM_TRAILING_LIMITERS = (
    r"\bis not proven\b",
    r"\bare not proven\b",
    r"\bnot proven\b",
    r"\bnot enabled\b",
    r"\bnot supported\b",
    r"\bremain(?:s)? out of scope\b",
    r"\bis out of scope\b",
    r"\bare out of scope\b",
    r"\bforbidden\b",
    r"\bblocked\b",
    r"\boverclaims?\b",
)
_CLAIM_LIMITER_DISTANCE = 140
_PINNED_DEPENDENCY = re.compile(r"^[A-Za-z0-9_.-]+==[^=].+")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def produce_p129_distribution_report(
    *,
    root: Path = _ROOT,
    reviewer_id: str = "independent-p129-verifier",
    builder_id: str = "autonomous-builder",
) -> dict[str, Any]:
    root = root.resolve()
    p122_release = _read_json(root / "evals/p122/release-evidence.json")
    security_report = _read_json(root / "evals/p122/security-report.json")
    vulnerability_report = _read_json(root / "evals/p122/vulnerability-audit.json")
    sbom = _read_json(root / "evals/p122/sbom.json")
    license_inventory = _read_json(root / "evals/p122/license-inventory.json")
    reproducible_build = _read_json(root / "evals/p122/reproducible-build.json")
    clean_install = _read_json(root / "evals/p122/clean-install.json")
    package_checksums = _read_json(root / "evals/p122/package-checksums.json")
    docs = _governed_docs(root)
    compatibility = _compatibility(root)
    imports = _import_contracts(root)
    packaging = _packaging_summary(reproducible_build, clean_install, package_checksums)
    security = _security_summary(root, security_report, vulnerability_report)
    supply_chain = _supply_chain_summary(sbom, license_inventory)
    authority = _authority_summary(p122_release)
    p122: dict[str, Any] = {
        "release_status": p122_release.get("release_status"),
        "release_evidence_hash": p122_release.get("release_evidence_hash"),
        "product_claim": p122_release.get("product_claim"),
        "public_limitation": p122_release.get("public_limitation"),
        "gates": p122_release.get("gates") if isinstance(p122_release.get("gates"), dict) else {},
    }
    gates = {
        "distinct_reviewer": bool(reviewer_id and builder_id and reviewer_id != builder_id),
        "p122_release_evidence_ready": p122_release.get("release_status") == "p122_open_source_local_rc"
        and _hash_like(p122_release.get("release_evidence_hash")),
        "governed_docs_valid": all(item.get("status") == "valid" for item in docs),
        "security_intake_defined": _security_policy_defined(root),
        "version_compatibility_defined": _compatibility_policy_defined(root),
        "packaging_reproducibility_evidence": packaging["reproducible_wheel_and_sdist"] is True
        and packaging["clean_install_contract_demo_uninstall"] is True,
        "stable_internal_imports_declared": imports["stable_internal_boundary_declared"] is True,
        "contract_refs_resolvable": imports["unresolved_contract_refs"] == [],
        "sbom_license_complete": supply_chain["sbom_completeness"] == 1.0
        and supply_chain["license_completeness"] == 1.0
        and supply_chain["unknown_license_count"] == 0
        and supply_chain["incompatible_license_count"] == 0,
        "security_release_blockers_zero": security["detected_secrets"] == 0
        and security["high_or_critical_security_findings"] == 0
        and security["high_or_critical_vulnerabilities"] == 0
        and security["unpinned_runtime_dependencies"] == 0
        and security["production_enabled_defaults"] == 0,
        "exact_nonlocal_authority_zero": authority["exact_nonlocal_authority_zero"] is True,
        "python_312_314_declared_or_pending": all(
            item["declared"] is True and item["status"] in {"available", "pending_unavailable"}
            for item in compatibility["python_versions"].values()
        ),
        "claim_language_bounded": _claim_language_bounded(root, p122),
    }
    report: dict[str, Any] = {
        "schema_version": P129_DISTRIBUTION_SCHEMA_VERSION,
        "phase": "P129",
        "status": "p129_distribution_maturity_ready" if all(gates.values()) else "p129_blocked",
        "product_claim": "OSS distribution maturity with local/mock/sandbox qualification",
        "public_limitation": (
            "Production autonomy, auth completion, credentials, live connector writes, production/staging mutation, "
            "operator replacement, and enterprise support readiness are not proven or enabled."
        ),
        "review": {"reviewer_id": reviewer_id, "builder_id": builder_id},
        "gates": gates,
        "governed_docs": docs,
        "planning_docs": _planning_docs(root),
        "p122_evidence": p122,
        "packaging": packaging,
        "security": security,
        "supply_chain": supply_chain,
        "imports": imports,
        "compatibility": compatibility,
        "authority": authority,
        "unresolved_risks": [
            "P129 aggregates local OSS distribution evidence only; it does not prove production operation.",
            "Unavailable declared Python interpreters remain pending_unavailable until executed on that interpreter.",
        ],
        "reasons": [f"{key} failed closed" for key, passed in gates.items() if not passed],
    }
    report["report_hash"] = stable_hash(report)
    return report


def produce_p129_release_evidence(
    *,
    root: Path = _ROOT,
    reviewer_id: str = "independent-p129-verifier",
    builder_id: str = "autonomous-builder",
) -> dict[str, Any]:
    distribution_report = produce_p129_distribution_report(root=root, reviewer_id=reviewer_id, builder_id=builder_id)
    evidence: dict[str, Any] = {
        "schema_version": P129_RELEASE_SCHEMA_VERSION,
        "release_id": "P129-005",
        "release_status": distribution_report["status"],
        "product_claim": distribution_report["product_claim"],
        "public_limitation": distribution_report["public_limitation"],
        "distribution_report_hash": distribution_report["report_hash"],
        "distribution_report": distribution_report,
        "gates": distribution_report["gates"],
        "authority": distribution_report["authority"],
        "review": distribution_report["review"],
        "reasons": distribution_report["reasons"],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p129_release_evidence(evidence: Mapping[str, Any], *, root: Path = _ROOT) -> dict[str, Any]:
    review = _mapping(evidence.get("review"))
    rebuilt = produce_p129_release_evidence(
        root=root,
        reviewer_id=str(review.get("reviewer_id", "")),
        builder_id=str(review.get("builder_id", "")),
    )
    expected_without_hash = {key: value for key, value in rebuilt.items() if key != "release_evidence_hash"}
    actual_without_hash = {key: value for key, value in evidence.items() if key != "release_evidence_hash"}
    checks = {
        "schema_current": evidence.get("schema_version") == P129_RELEASE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash(actual_without_hash),
        "all_fields_current": actual_without_hash == expected_without_hash,
        "distribution_report_hash_current": _mapping(evidence.get("distribution_report")).get("report_hash") == rebuilt["distribution_report_hash"],
        "release_qualified": evidence.get("release_status") == "p129_distribution_maturity_ready"
        and rebuilt.get("release_status") == "p129_distribution_maturity_ready",
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{key} failed closed" for key, passed in checks.items() if not passed]}


def _governed_docs(root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for relative in _REQUIRED_GOVERNED_DOCS:
        path = root / relative
        if not path.is_file():
            docs.append({"path": relative, "status": "missing", "hash": None, "missing_terms": list(_DOC_REQUIRED_TERMS[relative])})
            continue
        text = path.read_text(encoding="utf-8")
        missing_terms = [term for term in _DOC_REQUIRED_TERMS[relative] if term.lower() not in text.lower()]
        has_prohibited_claim = _has_unbounded_claim(text)
        docs.append(
            {
                "path": relative,
                "status": "valid" if not missing_terms and not has_prohibited_claim else "invalid",
                "hash": _file_hash(path),
                "missing_terms": missing_terms,
                "prohibited_claim_detected": has_prohibited_claim,
            }
        )
    return docs


def _planning_docs(root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for relative in _P129_PLANNING_DOCS:
        path = root / relative
        docs.append({"path": relative, "present": path.is_file(), "hash": _file_hash(path) if path.is_file() else None})
    return docs


def _packaging_summary(
    reproducible_build: Mapping[str, Any],
    clean_install: Mapping[str, Any],
    package_checksums: Mapping[str, Any],
) -> dict[str, Any]:
    wheel_hash = package_checksums.get("opscat-0.2.0-py3-none-any.whl")
    sdist_hash = package_checksums.get("opscat-0.2.0.tar.gz")
    clean_passed = (
        clean_install.get("install_exit_code") == 0
        and clean_install.get("demo_exit_code") == 0
        and clean_install.get("contracts_exit_code") == 0
        and clean_install.get("uninstall_exit_code") == 0
        and clean_install.get("import_residue_after_uninstall") is False
    )
    return {
        "wheel_hash": wheel_hash,
        "sdist_hash": sdist_hash,
        "package_checksum_count": len(package_checksums),
        "reproducible_build_hash": reproducible_build.get("report_hash"),
        "clean_install_hash": clean_install.get("report_hash"),
        "reproducible_wheel_and_sdist": reproducible_build.get("byte_reproducible") is True
        and _hash_like(wheel_hash)
        and _hash_like(sdist_hash)
        and _mapping(reproducible_build.get("checksums")) == dict(package_checksums),
        "clean_install_contract_demo_uninstall": clean_passed,
    }


def _security_summary(root: Path, security_report: Mapping[str, Any], vulnerability_report: Mapping[str, Any]) -> dict[str, Any]:
    findings = _sequence(security_report.get("findings"))
    severity_counts = _mapping(security_report.get("severity_counts"))
    return {
        "security_report_hash": security_report.get("report_hash"),
        "vulnerability_audit_hash": vulnerability_report.get("report_hash"),
        "detected_secrets": sum(1 for item in findings if str(_mapping(item).get("rule_id", "")).startswith("secret.")),
        "high_or_critical_security_findings": _int(severity_counts.get("high")) + _int(severity_counts.get("critical")),
        "high_or_critical_vulnerabilities": _int(vulnerability_report.get("vulnerability_count")),
        "unpinned_runtime_dependencies": _unpinned_runtime_dependencies(root),
        "production_enabled_defaults": sum(1 for item in findings if "production" in str(_mapping(item).get("rule_id", "")).lower()),
    }


def _supply_chain_summary(sbom: Mapping[str, Any], license_inventory: Mapping[str, Any]) -> dict[str, Any]:
    sbom_components = [_mapping(item) for item in _sequence(sbom.get("components"))]
    license_components = [_mapping(item) for item in _sequence(license_inventory.get("components"))]
    sbom_keys = {(str(item.get("name")), str(item.get("version"))) for item in sbom_components}
    license_keys = {(str(item.get("name")), str(item.get("version"))) for item in license_components}
    covered = sbom_keys & license_keys
    unknown = [
        item
        for item in license_components
        if not str(item.get("license", "")).strip() or "UNKNOWN" in str(item.get("license", "")).upper() or item.get("status") != "allowed"
    ]
    incompatible = [
        item
        for item in license_components
        if re.search(r"\b(?:AGPL|GPL)-(?:2|3)", str(item.get("license", "")).upper())
    ]
    return {
        "sbom_hash": stable_hash(sbom) if sbom else None,
        "license_inventory_hash": stable_hash(license_inventory) if license_inventory else None,
        "sbom_component_count": len(sbom_components),
        "license_component_count": len(license_components),
        "sbom_completeness": _ratio(len(sbom_keys), len(sbom_components)),
        "sbom_hash_coverage": _ratio(sum(1 for item in sbom_components if _sequence(item.get("hashes"))), len(sbom_components)),
        "license_completeness": _ratio(len(covered), len(sbom_keys)),
        "missing_license_components": sorted(f"{name}=={version}" for name, version in sbom_keys - license_keys),
        "unknown_license_count": len(unknown),
        "incompatible_license_count": len(incompatible),
    }


def _import_contracts(root: Path) -> dict[str, Any]:
    manifest = public_contract_manifest()
    contracts = [_mapping(item) for item in _sequence(manifest.get("contracts"))]
    unresolved: list[str] = []
    for contract in contracts:
        name = str(contract.get("name", "unknown"))
        module_name = str(contract.get("owner_module", ""))
        symbol = str(contract.get("owner_symbol", ""))
        if not module_name or not _module_symbol_resolves(module_name, symbol):
            unresolved.append(f"{name}:owner:{module_name}.{symbol}")
        for key in ("test_ref", "doc_ref"):
            ref = str(contract.get(key, "")).split("#", 1)[0]
            if ref and not (root / ref).exists():
                unresolved.append(f"{name}:{key}:{ref}")
    public_contracts_doc = root / "docs/public-contracts.md"
    doc_text = public_contracts_doc.read_text(encoding="utf-8") if public_contracts_doc.is_file() else ""
    stable_declared = (
        manifest.get("schema_version") == "opscat.public_contracts.v1"
        and all(contract.get("stability") == "stable-v1" for contract in contracts)
        and all(contract.get("nonlocal_authority_allowed") is False for contract in contracts)
        and "Everything else under `app.services` remains internal" in doc_text
    )
    return {
        "manifest_hash": manifest.get("manifest_hash"),
        "stable_contract_count": len(contracts),
        "stable_internal_boundary_declared": stable_declared,
        "unresolved_contract_refs": unresolved,
    }


def _compatibility(root: Path) -> dict[str, Any]:
    texts = _combined_text(root, ("pyproject.toml", "docs/install.md", "docs/installation.md", "docs/compatibility.md"))
    versions: dict[str, dict[str, Any]] = {}
    for version in _PYTHON_VERSIONS:
        declared = f"Python {version}" in texts or f":: Python :: {version}" in texts
        executable = shutil.which(f"python{version}") or shutil.which(f"python{version.replace('.', '')}")
        versions[version] = {
            "declared": declared,
            # Record a stable capability identifier, not a machine-specific
            # absolute path that makes promoted evidence non-reproducible.
            "executable": f"python{version}" if executable else None,
            "status": "available" if executable else ("pending_unavailable" if declared else "missing_declaration"),
        }
    return {
        "python_versions": versions,
        "policy_hash": _file_hash(root / "docs/compatibility.md") if (root / "docs/compatibility.md").is_file() else None,
        "migration_policy_ref": "docs/compatibility.md",
    }


def _authority_summary(p122_release: Mapping[str, Any]) -> dict[str, Any]:
    authority = _mapping(p122_release.get("authority"))
    exact_zero = authority.get("exact_nonlocal_authority_zero") is True and authority.get("nonzero_phases") == []
    return {
        "exact_nonlocal_authority_zero": exact_zero,
        "nonzero_authority_counters": {} if exact_zero else {"p122": list(_sequence(authority.get("nonzero_phases")))},
        "counters": zero_authority_counters(),
        "source": "evals/p122/release-evidence.json",
    }


def _security_policy_defined(root: Path) -> bool:
    text = (root / "SECURITY.md").read_text(encoding="utf-8") if (root / "SECURITY.md").is_file() else ""
    lowered = text.lower()
    return "private vulnerability" in lowered and "do not submit secrets" in lowered and "production credentials" in lowered


def _compatibility_policy_defined(root: Path) -> bool:
    text = (root / "docs/compatibility.md").read_text(encoding="utf-8") if (root / "docs/compatibility.md").is_file() else ""
    lowered = text.lower()
    return all(term in lowered for term in ("deprecation", "migration", "stable-v1")) and all(
        f"python {version}" in lowered for version in _PYTHON_VERSIONS
    )


def _claim_language_bounded(root: Path, p122: Mapping[str, Any]) -> bool:
    checked_text = json.dumps(p122, sort_keys=True) + "\n" + _combined_text(root, (*_REQUIRED_GOVERNED_DOCS, *_P129_PLANNING_DOCS))
    return not _has_unbounded_claim(checked_text)


def _has_unbounded_claim(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text)
    for match in _PROHIBITED_CLAIMS.finditer(normalized):
        if _claim_is_explicitly_limited(normalized, match):
            continue
        return True
    return False


def _claim_is_explicitly_limited(text: str, match: re.Match[str]) -> bool:
    leading_context = text[max(0, match.start() - _CLAIM_LIMITER_DISTANCE) : match.start()].lower()
    trailing_context = text[match.end() : match.end() + _CLAIM_LIMITER_DISTANCE].lower()
    return any(re.search(pattern + rf"[\s\S]{{0,{_CLAIM_LIMITER_DISTANCE}}}$", leading_context) for pattern in _CLAIM_LIMITERS) or any(
        re.search(rf"^[\s\S]{{0,{_CLAIM_LIMITER_DISTANCE}}}" + pattern, trailing_context) for pattern in _CLAIM_TRAILING_LIMITERS
    )


def _unpinned_runtime_dependencies(root: Path) -> int:
    pyproject = _read_toml(root / "pyproject.toml")
    dependencies = _sequence(_mapping(pyproject.get("project")).get("dependencies"))
    lock = _read_toml(root / "uv.lock")
    locked_names = {
        str(_mapping(package).get("name")).lower()
        for package in _sequence(lock.get("package"))
        if _mapping(package).get("name") and _mapping(package).get("version")
    }
    unpinned = 0
    for dependency in dependencies:
        spec = str(dependency)
        name = re.split(r"[<>=!~;\[]", spec, maxsplit=1)[0].strip().lower()
        if _PINNED_DEPENDENCY.fullmatch(spec) is None and name not in locked_names:
            unpinned += 1
    return unpinned


def _module_symbol_resolves(module_name: str, symbol: str) -> bool:
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return bool(symbol) and hasattr(module, symbol)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_like(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list | tuple) else []


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _combined_text(root: Path, relatives: Sequence[str]) -> str:
    chunks: list[str] = []
    for relative in relatives:
        path = root / relative
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)
