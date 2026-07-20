"""Pure-Python P176 runtime artifact producer.

The producer owns the handoff from a dependency-injected runtime harness to the
existing disposable live-lab bridge artifacts. It performs no provider calls by
itself; all live observations come from injected collaborators.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.services.p147_p152_contracts import file_hash, stable_hash
from app.services.p176_campaign import generate_p176_campaign, validate_p176_campaign
from app.services.p176_contracts import P176ContractError
from app.services.p176_evaluator import SAFETY_COUNTER_KEYS
from app.services.p176_evidence import P176EvidenceError, append_evidence_record, validate_evidence_chain
from app.services.p176_live_bridge import (
    AGENT_VISIBLE_LEDGER_PATH,
    BILLING_REPORT_PATH,
    CANONICAL_INPUT_MANIFEST_PATH,
    EPISODE_OBSERVATIONS_PATH,
    EVALUATOR_ONLY_LEDGER_PATH,
    FAULT_REGISTRY_PATH,
    HEALTHY_WINDOW_OBSERVATIONS_PATH,
    LIVE_SAFETY_COUNTER_KEYS,
    LIVE_SAFETY_REPORT_PATH,
    PROJECT_BINDING_PATH,
    RUN_INPUT_MANIFEST_PATH,
    TEARDOWN_PROOF_PATH,
    P176LiveBridgeError,
    load_json,
    load_jsonl,
    write_json,
    write_jsonl,
)
from app.services.p176_live_gates import (
    BUDGET_ALERT_AMOUNT_KRW,
    FORECAST_UNCERTAINTY_MARGIN,
    HARD_STOP_AMOUNT_KRW,
    HARNESS_PRINCIPAL_TEMPLATE,
    MAX_POLL_AGE_SECONDS,
    POLL_INTERVAL_SECONDS,
    P176LiveGateError,
    build_fault_registry,
    build_live_safety_report,
    validate_billing_report,
    validate_teardown_proof,
)


class P176RuntimeBridgeError(ValueError):
    """Raised when runtime-produced P176 artifacts fail closed."""


COLLECTION_IN_PROGRESS_PATH = "runtime-collection-in-progress.json"
EPISODE_PHASE_CHECKPOINT_PATH = "runtime-episode-phase-checkpoint.json"
COLLECTION_RECEIPT_PATH = "runtime-collection-receipt.json"
FINALIZATION_RECEIPT_PATH = "runtime-finalization-receipt.json"
COLLECTION_ARTIFACT_PATHS = (
    RUN_INPUT_MANIFEST_PATH,
    PROJECT_BINDING_PATH,
    FAULT_REGISTRY_PATH,
    LIVE_SAFETY_REPORT_PATH,
    AGENT_VISIBLE_LEDGER_PATH,
    EVALUATOR_ONLY_LEDGER_PATH,
    EPISODE_OBSERVATIONS_PATH,
    HEALTHY_WINDOW_OBSERVATIONS_PATH,
)
FINALIZATION_ARTIFACT_PATHS = (BILLING_REPORT_PATH, TEARDOWN_PROOF_PATH)
EPISODE_PHASE_ARTIFACT_PATHS = (
    AGENT_VISIBLE_LEDGER_PATH,
    EVALUATOR_ONLY_LEDGER_PATH,
    EPISODE_OBSERVATIONS_PATH,
)
EVIDENCE_SOURCE_CLASSES = (
    "metrics",
    "logs",
    "traces",
    "deploy_history",
    "host_state",
    "container_state",
    "topology",
    "dependency_health",
)
EPISODE_EVIDENCE_SOURCE_CLASSES = {
    "api": ("logs", "traces"),
    "worker": ("logs", "metrics"),
    "database": ("metrics", "traces"),
    "cache_queue": ("metrics", "dependency_health"),
    "deployment": ("deploy_history", "container_state"),
    "network": ("host_state", "dependency_health"),
    "dependency": ("traces", "dependency_health"),
}


def run_p176_runtime_bridge(
    *,
    run_dir: Path,
    target_endpoint: str,
    observer_endpoint: str,
) -> dict[str, Any]:
    """Execute one explicit runtime lifecycle phase through real provider wiring.

    Collection is the safe default. Finalization is a separate opt-in phase so
    billing and teardown evidence cannot be queried or claimed before collection
    has been hash-sealed.
    """

    _validate_iap_loopback_endpoint(target_endpoint, label="target")
    _validate_iap_loopback_endpoint(observer_endpoint, label="observer")
    phase = os.environ.get("P176_RUNTIME_PHASE", "collect")
    if phase not in {"collect", "finalize"}:
        raise P176RuntimeBridgeError("runtime_phase_invalid")

    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    producer = _build_runtime_producer(
        run_dir=directory,
        target_endpoint=target_endpoint,
        observer_endpoint=observer_endpoint,
    )
    if phase == "collect":
        producer.collect(directory)
        _require_runtime_receipt(directory / COLLECTION_RECEIPT_PATH, "collection_receipt_missing")
        return {
            "status": "runtime_collection_complete",
            "phase": "collect",
            "run_dir": str(directory),
        }

    producer.finalize(directory, now=datetime.now(UTC))
    _require_runtime_receipt(directory / FINALIZATION_RECEIPT_PATH, "finalization_receipt_missing")
    return {
        "status": "runtime_finalization_complete",
        "phase": "finalize",
        "run_dir": str(directory),
    }


def _validate_iap_loopback_endpoint(endpoint: str, *, label: str) -> None:
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise P176RuntimeBridgeError(f"{label}_endpoint_not_allowed") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise P176RuntimeBridgeError(f"{label}_endpoint_not_allowed")


def _require_runtime_receipt(path: Path, error: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise P176RuntimeBridgeError(error)


def _build_runtime_producer(
    *,
    run_dir: Path,
    target_endpoint: str,
    observer_endpoint: str,
) -> P176RuntimeArtifactProducer:
    from app.services.p176_live_runtime import build_runtime_producer_from_environment

    try:
        return build_runtime_producer_from_environment(
            run_dir=run_dir,
            target_endpoint=target_endpoint,
            observer_endpoint=observer_endpoint,
        )
    except RuntimeError as exc:
        raise P176RuntimeBridgeError(f"runtime_provider_factory_invalid:{exc}") from exc


@dataclass(frozen=True)
class P176RuntimeConfig:
    run_id: str
    project_id: str
    p174_control_clone_hash: str
    reviewed_apply_plan_hash: str
    reviewed_teardown_plan_hash: str
    reviewed_cost_cutoff_apply_plan_hash: str
    reviewed_cost_cutoff_destroy_plan_hash: str
    billing_account_id: str
    budget_resource_name: str
    observer_principal: str
    harness_fault_principal: str
    opscat_principal: str = ""
    expected_project_prefix: str = "opscat-p176-live-"
    billing_budget_amount_krw: int = 30_000
    region_zone: str = "asia-northeast3-a"


@dataclass(frozen=True)
class EvidenceSnapshot:
    observed_at: str
    received_at: str
    freshness_bound_seconds: int
    content_hash: str
    redaction_receipt_hash: str
    summary: Mapping[str, Any]
    evaluator_context_hash: str | None = None


@dataclass(frozen=True)
class FaultExecution:
    fault_lease_id: str
    mutation_principal: str
    mutation_executed: bool
    incident_detected: bool
    diagnosed_family_id: str | None
    routed_service_id: str | None
    recovery_observed: bool
    residual_effect_count: int
    evidence_citations: tuple[str, ...]
    human_required: bool
    deadman_receipt_hash: str
    cleanup_receipt_hash: str
    residual_effect_proof_hash: str
    agent_evidence: Mapping[str, EvidenceSnapshot]
    evaluator_evidence: Mapping[str, EvidenceSnapshot]


@dataclass(frozen=True)
class HealthyObservation:
    false_alert: bool
    false_action: bool
    agent_evidence: Mapping[str, EvidenceSnapshot] | None = None
    evaluator_evidence: Mapping[str, EvidenceSnapshot] | None = None


@dataclass(frozen=True)
class BillingSnapshot:
    latest_poll_at: str
    latest_actual_cost_krw: int | float
    latest_forecast_cost_krw: int | float
    provider_response_hash: str
    poll_count: int
    stale_poll_count: int = 0
    stop_triggered: bool = False
    source: str = "gcp_cloud_billing_api"


@dataclass(frozen=True)
class TeardownSnapshot:
    reviewed_apply_started_at: str
    collection_started_at: str
    collection_completed_at: str
    terminal_stop_at: str
    teardown_started_at: str
    teardown_completed_at: str
    concurrency_plan_proven: bool
    remaining_non_billing_resource_count: int
    residual_effect_count: int
    final_cost_snapshot_hash: str


class EvidenceProvider(Protocol):
    def collect(self, *, ledger_name: str, source_class: str) -> EvidenceSnapshot:
        ...


class FaultHarness(Protocol):
    def execute_fault(
        self,
        *,
        episode: Mapping[str, Any],
        fault_verb: str,
        harness_principal: str,
    ) -> FaultExecution:
        ...


class HealthyObserver(Protocol):
    def observe_window(self, *, window: Mapping[str, Any]) -> HealthyObservation:
        ...


class BillingProvider(Protocol):
    def latest_billing(self) -> BillingSnapshot:
        ...


class TeardownProvider(Protocol):
    def teardown_proof(self) -> TeardownSnapshot:
        ...


class SafetyMonitor(Protocol):
    def live_safety(self) -> Mapping[str, int]:
        ...


@dataclass(frozen=True)
class P176RuntimeArtifactProducer:
    config: P176RuntimeConfig
    evidence_provider: EvidenceProvider
    fault_harness: FaultHarness
    healthy_observer: HealthyObserver
    billing_provider: BillingProvider
    teardown_provider: TeardownProvider
    safety_monitor: SafetyMonitor
    campaign: Mapping[str, Any] | None = None

    def produce(self, run_dir: str | Path, *, now: datetime) -> Path:
        self.collect(run_dir)
        return self.finalize(run_dir, now=now)

    def collect(self, run_dir: str | Path) -> Path:
        """Collect and hash-seal runtime evidence without post-run provider calls."""
        directory = Path(run_dir)
        self._ensure_run_dir(directory)
        receipt_path = directory / COLLECTION_RECEIPT_PATH
        if _path_present(receipt_path):
            self._verify_collection_receipt(directory)
            self._remove_completed_collection_markers(directory)
            return directory

        canonical_campaign = generate_p176_campaign()
        try:
            campaign = validate_p176_campaign(self.campaign or canonical_campaign)
        except P176ContractError as exc:
            raise P176RuntimeBridgeError(f"campaign_invalid:{exc}") from exc
        episodes = list(campaign["episodes"])
        healthy_windows = list(campaign["healthy_windows"])
        if len(episodes) != 480 or len(healthy_windows) != 240:
            raise P176RuntimeBridgeError("campaign_cardinality_invalid")
        if episodes != canonical_campaign["episodes"] or healthy_windows != canonical_campaign["healthy_windows"]:
            raise P176RuntimeBridgeError("canonical_campaign_order_invalid")

        project_binding = self._build_project_binding()
        fault_registry = build_fault_registry(phase="p176", run_id=self.config.run_id, project_id=self.config.project_id)
        if fault_registry["harness_fault_principal"] != self.config.harness_fault_principal:
            raise P176RuntimeBridgeError("harness_fault_principal_invalid")

        in_progress_path = directory / COLLECTION_IN_PROGRESS_PATH
        checkpoint_path = directory / EPISODE_PHASE_CHECKPOINT_PATH
        has_in_progress = _path_present(in_progress_path)
        has_checkpoint = _path_present(checkpoint_path)
        has_collection_artifact = any(_path_present(directory / path) for path in COLLECTION_ARTIFACT_PATHS)
        has_finalization_artifact = any(
            _path_present(directory / path) for path in (*FINALIZATION_ARTIFACT_PATHS, FINALIZATION_RECEIPT_PATH)
        )
        if has_finalization_artifact or has_in_progress != has_checkpoint:
            raise P176RuntimeBridgeError("collection_partial_state")

        if has_checkpoint:
            agent_ledger, evaluator_ledger, episode_observations = self._load_episode_phase_checkpoint(
                directory,
                campaign=campaign,
                episodes=episodes,
            )
            self._build_live_safety_report()
        else:
            if has_collection_artifact:
                raise P176RuntimeBridgeError("collection_partial_state")
            in_progress = _self_hash(
                {
                    "schema_version": "p176.runtime_collection_in_progress.v1",
                    "phase": "p176",
                    "run_id": self.config.run_id,
                    "project_id": self.config.project_id,
                    "runtime_config_hash": self._runtime_config_hash(),
                    "campaign_hash": campaign["campaign_hash"],
                    "in_progress_hash": "",
                },
                "in_progress_hash",
            )
            write_json(in_progress_path, in_progress)
            agent_ledger = self._build_ledger("agent_visible")
            evaluator_ledger = self._build_ledger("evaluator_only")
            episode_observations = self._build_episode_observations(
                episodes,
                fault_registry,
                agent_ledger,
                evaluator_ledger,
            )
            self._build_live_safety_report()
            self._write_episode_phase_checkpoint(
                directory,
                campaign=campaign,
                agent_ledger=agent_ledger,
                evaluator_ledger=evaluator_ledger,
                episode_observations=episode_observations,
            )

        healthy_observations = self._build_healthy_observations(
            healthy_windows,
            agent_ledger,
            evaluator_ledger,
        )
        self._validate_ledger(agent_ledger, "agent_visible")
        self._validate_ledger(evaluator_ledger, "evaluator_only")
        live_safety_report = self._build_live_safety_report()

        self._copy_input_manifest(directory)
        write_json(directory / PROJECT_BINDING_PATH, project_binding)
        write_json(directory / FAULT_REGISTRY_PATH, fault_registry)
        write_json(directory / LIVE_SAFETY_REPORT_PATH, live_safety_report)
        write_jsonl(directory / AGENT_VISIBLE_LEDGER_PATH, agent_ledger)
        write_jsonl(directory / EVALUATOR_ONLY_LEDGER_PATH, evaluator_ledger)
        write_jsonl(directory / EPISODE_OBSERVATIONS_PATH, episode_observations)
        write_jsonl(directory / HEALTHY_WINDOW_OBSERVATIONS_PATH, healthy_observations)
        receipt = _self_hash(
            {
                "schema_version": "p176.runtime_collection_receipt.v1",
                "phase": "p176",
                "run_id": self.config.run_id,
                "project_id": self.config.project_id,
                "runtime_config_hash": self._runtime_config_hash(),
                "artifact_hashes": _artifact_hashes(directory, COLLECTION_ARTIFACT_PATHS),
                "collection_receipt_hash": "",
            },
            "collection_receipt_hash",
        )
        write_json(receipt_path, receipt)
        checkpoint_path.unlink()
        in_progress_path.unlink()
        return directory

    @staticmethod
    def _remove_completed_collection_markers(directory: Path) -> None:
        for path in (
            directory / EPISODE_PHASE_CHECKPOINT_PATH,
            directory / COLLECTION_IN_PROGRESS_PATH,
        ):
            if not _path_present(path):
                continue
            if not path.is_file() or path.is_symlink():
                raise P176RuntimeBridgeError("completed_collection_marker_unsafe")
            path.unlink()

    def _write_episode_phase_checkpoint(
        self,
        directory: Path,
        *,
        campaign: Mapping[str, Any],
        agent_ledger: Sequence[Mapping[str, Any]],
        evaluator_ledger: Sequence[Mapping[str, Any]],
        episode_observations: Sequence[Mapping[str, Any]],
    ) -> None:
        write_jsonl(directory / AGENT_VISIBLE_LEDGER_PATH, agent_ledger)
        write_jsonl(directory / EVALUATOR_ONLY_LEDGER_PATH, evaluator_ledger)
        write_jsonl(directory / EPISODE_OBSERVATIONS_PATH, episode_observations)
        checkpoint = _self_hash(
            {
                "schema_version": "p176.runtime_episode_phase_checkpoint.v1",
                "phase": "p176",
                "run_id": self.config.run_id,
                "project_id": self.config.project_id,
                "runtime_config_hash": self._runtime_config_hash(),
                "campaign_hash": campaign["campaign_hash"],
                "completed_episode_count": len(episode_observations),
                "artifact_hashes": _artifact_hashes(directory, EPISODE_PHASE_ARTIFACT_PATHS),
                "checkpoint_hash": "",
            },
            "checkpoint_hash",
        )
        write_json(directory / EPISODE_PHASE_CHECKPOINT_PATH, checkpoint)

    def _load_episode_phase_checkpoint(
        self,
        directory: Path,
        *,
        campaign: Mapping[str, Any],
        episodes: Sequence[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        checkpoint = _load_receipt(
            directory / EPISODE_PHASE_CHECKPOINT_PATH,
            "episode_phase_checkpoint_missing",
        )
        _verify_receipt_shape(
            checkpoint,
            expected_fields={
                "schema_version",
                "phase",
                "run_id",
                "project_id",
                "runtime_config_hash",
                "campaign_hash",
                "completed_episode_count",
                "artifact_hashes",
                "checkpoint_hash",
            },
            expected_schema="p176.runtime_episode_phase_checkpoint.v1",
            hash_field="checkpoint_hash",
            run_id=self.config.run_id,
        )
        if (
            checkpoint["project_id"] != self.config.project_id
            or checkpoint["runtime_config_hash"] != self._runtime_config_hash()
            or checkpoint["campaign_hash"] != campaign["campaign_hash"]
            or checkpoint["completed_episode_count"] != len(episodes)
        ):
            raise P176RuntimeBridgeError("episode_phase_checkpoint_binding_invalid")
        _verify_artifact_hashes(
            directory,
            checkpoint.get("artifact_hashes"),
            EPISODE_PHASE_ARTIFACT_PATHS,
            "episode_phase_checkpoint_artifact_hash_mismatch",
        )
        try:
            agent_ledger = load_jsonl(directory / AGENT_VISIBLE_LEDGER_PATH)
            evaluator_ledger = load_jsonl(directory / EVALUATOR_ONLY_LEDGER_PATH)
            episode_observations = load_jsonl(directory / EPISODE_OBSERVATIONS_PATH)
        except P176LiveBridgeError as exc:
            raise P176RuntimeBridgeError(f"episode_phase_checkpoint_invalid:{exc}") from exc
        self._validate_ledger(agent_ledger, "agent_visible")
        self._validate_ledger(evaluator_ledger, "evaluator_only")
        if len(episode_observations) != len(episodes):
            raise P176RuntimeBridgeError("episode_phase_checkpoint_observations_invalid")
        for row, episode in zip(episode_observations, episodes, strict=True):
            if (
                row.get("schema_version") != "p176.live_episode_observation.v1"
                or row.get("run_id") != self.config.run_id
                or row.get("episode_id") != episode["episode_id"]
                or row.get("observation_hash")
                != stable_hash({key: value for key, value in row.items() if key != "observation_hash"})
            ):
                raise P176RuntimeBridgeError("episode_phase_checkpoint_observations_invalid")
        return agent_ledger, evaluator_ledger, episode_observations

    def finalize(self, run_dir: str | Path, *, now: datetime) -> Path:
        """Add billing and teardown proof only after immutable collection exists."""
        directory = Path(run_dir)
        self._ensure_run_dir(directory, create=False)
        collection_receipt = self._verify_collection_receipt(directory)
        finalization_path = directory / FINALIZATION_RECEIPT_PATH
        if _path_present(finalization_path):
            self._verify_finalization_receipt(directory, collection_receipt=collection_receipt)
            return directory
        if any(_path_present(directory / path) for path in FINALIZATION_ARTIFACT_PATHS):
            raise P176RuntimeBridgeError("finalization_partial_state")

        billing_report = self._build_billing_report(now=now)
        teardown_proof = self._build_teardown_proof()
        write_json(directory / BILLING_REPORT_PATH, billing_report)
        write_json(directory / TEARDOWN_PROOF_PATH, teardown_proof)
        receipt = _self_hash(
            {
                "schema_version": "p176.runtime_finalization_receipt.v1",
                "phase": "p176",
                "run_id": self.config.run_id,
                "collection_receipt_hash": collection_receipt["collection_receipt_hash"],
                "artifact_hashes": _artifact_hashes(directory, FINALIZATION_ARTIFACT_PATHS),
                "finalized_at": now.isoformat().replace("+00:00", "Z"),
                "finalization_receipt_hash": "",
            },
            "finalization_receipt_hash",
        )
        write_json(finalization_path, receipt)
        return directory

    def _verify_collection_receipt(self, directory: Path) -> dict[str, Any]:
        receipt = _load_receipt(directory / COLLECTION_RECEIPT_PATH, "collection_receipt_missing")
        _verify_receipt_shape(
            receipt,
            expected_fields={
                "schema_version",
                "phase",
                "run_id",
                "project_id",
                "runtime_config_hash",
                "artifact_hashes",
                "collection_receipt_hash",
            },
            expected_schema="p176.runtime_collection_receipt.v1",
            hash_field="collection_receipt_hash",
            run_id=self.config.run_id,
        )
        if receipt["project_id"] != self.config.project_id:
            raise P176RuntimeBridgeError("collection_project_id_mismatch")
        if receipt["runtime_config_hash"] != self._runtime_config_hash():
            raise P176RuntimeBridgeError("collection_config_mismatch")
        _verify_artifact_hashes(
            directory,
            receipt.get("artifact_hashes"),
            COLLECTION_ARTIFACT_PATHS,
            "collection_artifact_hash_mismatch",
        )
        return receipt

    def _verify_finalization_receipt(self, directory: Path, *, collection_receipt: Mapping[str, Any]) -> dict[str, Any]:
        receipt = _load_receipt(directory / FINALIZATION_RECEIPT_PATH, "finalization_receipt_missing")
        _verify_receipt_shape(
            receipt,
            expected_fields={
                "schema_version",
                "phase",
                "run_id",
                "collection_receipt_hash",
                "artifact_hashes",
                "finalized_at",
                "finalization_receipt_hash",
            },
            expected_schema="p176.runtime_finalization_receipt.v1",
            hash_field="finalization_receipt_hash",
            run_id=self.config.run_id,
        )
        if receipt["collection_receipt_hash"] != collection_receipt["collection_receipt_hash"]:
            raise P176RuntimeBridgeError("finalization_collection_receipt_mismatch")
        _verify_artifact_hashes(
            directory,
            receipt.get("artifact_hashes"),
            FINALIZATION_ARTIFACT_PATHS,
            "finalization_artifact_hash_mismatch",
        )
        return receipt

    @staticmethod
    def _ensure_run_dir(directory: Path, *, create: bool = True) -> None:
        if directory.is_symlink():
            raise P176RuntimeBridgeError(f"run_dir_unsafe:{directory}")
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise P176RuntimeBridgeError(f"run_dir_missing:{directory}")

    def _runtime_config_hash(self) -> str:
        return stable_hash(vars(self.config))

    def _build_ledger(self, ledger_name: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        self._append_evidence_records(records, ledger_name=ledger_name, source_classes=EVIDENCE_SOURCE_CLASSES)
        self._validate_ledger(records, ledger_name)
        return records

    def _append_evidence_records(
        self,
        records: list[dict[str, Any]],
        *,
        ledger_name: str,
        source_classes: Sequence[str],
        snapshots: Mapping[str, EvidenceSnapshot] | None = None,
    ) -> list[str]:
        if snapshots is not None and set(snapshots) != set(source_classes):
            raise P176RuntimeBridgeError("episode_evidence_source_mismatch")
        appended_hashes: list[str] = []
        for source_class in source_classes:
            snapshot = (
                snapshots[source_class]
                if snapshots is not None
                else self.evidence_provider.collect(ledger_name=ledger_name, source_class=source_class)
            )
            try:
                record = append_evidence_record(
                    previous=records[-1] if records else None,
                    ledger_name=ledger_name,
                    source_class=source_class,
                    source_id=f"{ledger_name}/{source_class}/{len(records) + 1}",
                    observed_at=snapshot.observed_at,
                    received_at=snapshot.received_at,
                    freshness_bound_seconds=snapshot.freshness_bound_seconds,
                    content_hash=snapshot.content_hash,
                    redaction_receipt_hash=snapshot.redaction_receipt_hash,
                    summary=snapshot.summary,
                    evaluator_context_hash=snapshot.evaluator_context_hash,
                )
            except P176EvidenceError as exc:
                raise P176RuntimeBridgeError(f"evidence_record_invalid:{exc}") from exc
            records.append(record)
            appended_hashes.append(str(record["record_hash"]))
        return appended_hashes

    @staticmethod
    def _validate_ledger(records: Sequence[Mapping[str, Any]], ledger_name: str) -> None:
        try:
            validate_evidence_chain(records, ledger_name=ledger_name, require_all_source_classes=True)
        except P176EvidenceError as exc:
            raise P176RuntimeBridgeError(f"evidence_chain_invalid:{exc}") from exc

    def _build_episode_observations(
        self,
        episodes: Sequence[Mapping[str, Any]],
        fault_registry: Mapping[str, Any],
        agent_ledger: list[dict[str, Any]],
        evaluator_ledger: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        allowed_verbs = set(fault_registry["allowed_fault_verbs"])
        seen_leases: set[str] = set()
        rows: list[dict[str, Any]] = []
        for episode in episodes:
            fault_verb = _fault_verb_for_episode(episode)
            if fault_verb not in allowed_verbs:
                raise P176RuntimeBridgeError("fault_verb_not_registered")
            execution = self.fault_harness.execute_fault(
                episode=episode,
                fault_verb=fault_verb,
                harness_principal=self.config.harness_fault_principal,
            )
            if execution.mutation_principal != self.config.harness_fault_principal:
                raise P176RuntimeBridgeError("mutation_principal_not_harness")
            if execution.fault_lease_id in seen_leases:
                raise P176RuntimeBridgeError("fault_lease_replayed")
            seen_leases.add(execution.fault_lease_id)
            for field, proof_type, actual in (
                ("deadman_receipt_hash", "deadman_receipt", execution.deadman_receipt_hash),
                ("cleanup_receipt_hash", "cleanup_receipt", execution.cleanup_receipt_hash),
                ("residual_effect_proof_hash", "residual_effect_proof", execution.residual_effect_proof_hash),
            ):
                expected = fault_proof_hash(
                    run_id=self.config.run_id,
                    episode_id=str(episode["episode_id"]),
                    fault_lease_id=execution.fault_lease_id,
                    proof_type=proof_type,
                )
                if actual != expected:
                    raise P176RuntimeBridgeError(f"{field}_not_bound")
            source_classes = EPISODE_EVIDENCE_SOURCE_CLASSES.get(str(episode["primary_layer"]))
            if source_classes is None:
                raise P176RuntimeBridgeError("episode_primary_layer_unsupported")
            agent_hashes = self._append_evidence_records(
                agent_ledger,
                ledger_name="agent_visible",
                source_classes=source_classes,
                snapshots=execution.agent_evidence,
            )
            evaluator_hashes = self._append_evidence_records(
                evaluator_ledger,
                ledger_name="evaluator_only",
                source_classes=source_classes,
                snapshots=execution.evaluator_evidence,
            )
            cited_hashes = set(execution.evidence_citations)
            available_hashes = {snapshot.content_hash for snapshot in execution.agent_evidence.values()}
            citation_supported = bool(cited_hashes) and cited_hashes <= available_hashes
            recovery_verified = execution.recovery_observed and execution.residual_effect_count == 0
            row = {
                "schema_version": "p176.live_episode_observation.v1",
                "run_id": self.config.run_id,
                "episode_id": episode["episode_id"],
                "family_id": episode["family_id"],
                "primary_layer": episode["primary_layer"],
                "service_id": episode["service_id"],
                "severity": episode["severity"],
                "traffic_shape": episode["traffic_shape"],
                "cross_service": episode["cross_service"],
                "pair_class": episode["pair_class"],
                "source_service_id": episode["source_service_id"],
                "downstream_service_id": episode["downstream_service_id"],
                "fault_lease_id": execution.fault_lease_id,
                "fault_verb": fault_verb,
                "incident_detected": execution.incident_detected,
                "diagnosis_correct": execution.diagnosed_family_id == episode["family_id"],
                "routing_correct": execution.routed_service_id == episode["service_id"],
                "recovery_verified": recovery_verified,
                "collateral_impact": execution.residual_effect_count != 0,
                "citation_supported": citation_supported,
                "human_required": execution.human_required,
                "mutation_executed": execution.mutation_executed,
                "agent_visible_record_hashes": agent_hashes,
                "evaluator_only_record_hashes": evaluator_hashes,
                "deadman_receipt_hash": execution.deadman_receipt_hash,
                "cleanup_receipt_hash": execution.cleanup_receipt_hash,
                "residual_effect_proof_hash": execution.residual_effect_proof_hash,
                "observation_hash": "",
            }
            rows.append(_self_hash(row, "observation_hash"))
        return rows

    def _build_healthy_observations(
        self,
        healthy_windows: Sequence[Mapping[str, Any]],
        agent_ledger: list[dict[str, Any]],
        evaluator_ledger: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for window in healthy_windows:
            observation = self.healthy_observer.observe_window(window=window)
            source_classes = (str(window["telemetry_class"]),)
            agent_hashes = self._append_evidence_records(
                agent_ledger,
                ledger_name="agent_visible",
                source_classes=source_classes,
                snapshots=observation.agent_evidence,
            )
            evaluator_hashes = self._append_evidence_records(
                evaluator_ledger,
                ledger_name="evaluator_only",
                source_classes=source_classes,
                snapshots=observation.evaluator_evidence,
            )
            row = {
                "schema_version": "p176.live_healthy_window_observation.v1",
                "run_id": self.config.run_id,
                "window_id": window["window_id"],
                "telemetry_class": window["telemetry_class"],
                "service_id": window["service_id"],
                "noisy": window["noisy"],
                "false_alert": observation.false_alert,
                "false_action": observation.false_action,
                "agent_visible_record_hashes": agent_hashes,
                "evaluator_only_record_hashes": evaluator_hashes,
                "observation_hash": "",
            }
            rows.append(_self_hash(row, "observation_hash"))
        return rows

    def _build_project_binding(self) -> dict[str, Any]:
        expected_harness = HARNESS_PRINCIPAL_TEMPLATE.format(project_id=self.config.project_id)
        if self.config.harness_fault_principal != expected_harness:
            raise P176RuntimeBridgeError("harness_fault_principal_invalid")
        binding = {
            "schema_version": "p176.live_project_binding.v1",
            "phase": "p176",
            "run_id": self.config.run_id,
            "project_id": self.config.project_id,
            "expected_project_prefix": self.config.expected_project_prefix,
            "p174_control_clone_hash": self.config.p174_control_clone_hash,
            "reviewed_apply_plan_hash": self.config.reviewed_apply_plan_hash,
            "reviewed_cost_cutoff_apply_plan_hash": self.config.reviewed_cost_cutoff_apply_plan_hash,
            "reviewed_cost_cutoff_destroy_plan_hash": self.config.reviewed_cost_cutoff_destroy_plan_hash,
            "billing_budget_amount_krw": self.config.billing_budget_amount_krw,
            "billing_account_id": self.config.billing_account_id,
            "budget_resource_name": self.config.budget_resource_name,
            "region_zone": self.config.region_zone,
            "observer_principal": self.config.observer_principal,
            "harness_fault_principal": self.config.harness_fault_principal,
            "opscat_principal": self.config.opscat_principal,
            "binding_hash": "",
        }
        return _self_hash(binding, "binding_hash")

    def _build_billing_report(self, *, now: datetime) -> dict[str, Any]:
        snapshot = self.billing_provider.latest_billing()
        receipt = _self_hash(
            {
                "schema_version": "p176.live_billing_poll_receipt.v1",
                "source": snapshot.source,
                "run_id": self.config.run_id,
                "project_id": self.config.project_id,
                "billing_account_id": self.config.billing_account_id,
                "budget_resource_name": self.config.budget_resource_name,
                "polled_at": snapshot.latest_poll_at,
                "actual_cost_krw": snapshot.latest_actual_cost_krw,
                "forecast_cost_krw": snapshot.latest_forecast_cost_krw,
                "provider_response_hash": snapshot.provider_response_hash,
                "receipt_hash": "",
            },
            "receipt_hash",
        )
        report = _self_hash(
            {
                "schema_version": "p176.live_billing_report.v1",
                "phase": "p176",
                "run_id": self.config.run_id,
                "project_id": self.config.project_id,
                "billing_account_id": self.config.billing_account_id,
                "budget_resource_name": self.config.budget_resource_name,
                "poll_interval_seconds": POLL_INTERVAL_SECONDS,
                "max_poll_age_seconds": MAX_POLL_AGE_SECONDS,
                "budget_alert_amount_krw": BUDGET_ALERT_AMOUNT_KRW,
                "hard_stop_amount_krw": HARD_STOP_AMOUNT_KRW,
                "forecast_uncertainty_margin": FORECAST_UNCERTAINTY_MARGIN,
                "poll_count": snapshot.poll_count,
                "stale_poll_count": snapshot.stale_poll_count,
                "latest_poll_at": snapshot.latest_poll_at,
                "latest_actual_cost_krw": snapshot.latest_actual_cost_krw,
                "latest_forecast_cost_krw": snapshot.latest_forecast_cost_krw,
                "stop_triggered": snapshot.stop_triggered,
                "latest_provider_poll_receipt": receipt,
                "billing_report_hash": "",
            },
            "billing_report_hash",
        )
        try:
            return validate_billing_report(report, now=now, expected_billing_account_id=self.config.billing_account_id)
        except P176LiveGateError as exc:
            raise P176RuntimeBridgeError(f"billing_report_invalid:{exc}") from exc

    def _build_teardown_proof(self) -> dict[str, Any]:
        snapshot = self.teardown_provider.teardown_proof()
        proof = _self_hash(
            {
                "schema_version": "p176.live_teardown_proof.v1",
                "phase": "p176",
                "run_id": self.config.run_id,
                "reviewed_teardown_plan_hash": self.config.reviewed_teardown_plan_hash,
                "reviewed_apply_started_at": snapshot.reviewed_apply_started_at,
                "collection_started_at": snapshot.collection_started_at,
                "collection_completed_at": snapshot.collection_completed_at,
                "terminal_stop_at": snapshot.terminal_stop_at,
                "teardown_started_at": snapshot.teardown_started_at,
                "teardown_completed_at": snapshot.teardown_completed_at,
                "concurrency_plan_proven": snapshot.concurrency_plan_proven,
                "remaining_non_billing_resource_count": snapshot.remaining_non_billing_resource_count,
                "residual_effect_count": snapshot.residual_effect_count,
                "final_cost_snapshot_hash": snapshot.final_cost_snapshot_hash,
                "teardown_hash": "",
            },
            "teardown_hash",
        )
        try:
            return validate_teardown_proof(proof)
        except P176LiveGateError as exc:
            raise P176RuntimeBridgeError(f"teardown_proof_invalid:{exc}") from exc

    def _build_live_safety_report(self) -> dict[str, Any]:
        live_safety = dict(self.safety_monitor.live_safety())
        if set(live_safety) != set(LIVE_SAFETY_COUNTER_KEYS):
            raise P176RuntimeBridgeError("live_safety_keyset_invalid")
        if any(type(live_safety[key]) is not int or live_safety[key] != 0 for key in LIVE_SAFETY_COUNTER_KEYS):
            raise P176RuntimeBridgeError("live_safety_counter_nonzero")
        try:
            report = build_live_safety_report(phase="p176", run_id=self.config.run_id, live_safety=live_safety)
        except P176LiveGateError as exc:
            raise P176RuntimeBridgeError(f"live_safety_invalid:{exc}") from exc
        if any(report["canonical_projection"][key] != 0 for key in SAFETY_COUNTER_KEYS):
            raise P176RuntimeBridgeError("canonical_safety_counters_nonzero")
        return report

    @staticmethod
    def _copy_input_manifest(directory: Path) -> None:
        if not CANONICAL_INPUT_MANIFEST_PATH.is_file() or CANONICAL_INPUT_MANIFEST_PATH.is_symlink():
            raise P176RuntimeBridgeError("canonical_input_manifest_missing_or_unsafe")
        shutil.copyfile(CANONICAL_INPUT_MANIFEST_PATH, directory / RUN_INPUT_MANIFEST_PATH)


def fault_proof_hash(
    *,
    run_id: str,
    episode_id: str,
    fault_lease_id: str,
    proof_type: str,
) -> str:
    return stable_hash(
        {
            "schema_version": "p176.live_fault_proof_binding.v1",
            "run_id": run_id,
            "episode_id": episode_id,
            "fault_lease_id": fault_lease_id,
            "proof_type": proof_type,
        }
    )


def _fault_verb_for_episode(episode: Mapping[str, Any]) -> str:
    return f"inject_{str(episode['family_id']).split('-', 3)[3]}"


def _self_hash(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = stable_hash({key: item for key, item in result.items() if key != field})
    return result


def _path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _artifact_hashes(directory: Path, paths: Sequence[str]) -> dict[str, str]:
    return {path: file_hash(directory / path) for path in paths}


def _load_receipt(path: Path, missing_error: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise P176RuntimeBridgeError(missing_error)
    try:
        value = load_json(path)
    except P176LiveBridgeError as exc:
        raise P176RuntimeBridgeError(f"receipt_invalid:{exc}") from exc
    if not isinstance(value, dict):
        raise P176RuntimeBridgeError("receipt_invalid:not_object")
    return value


def _verify_receipt_shape(
    receipt: Mapping[str, Any],
    *,
    expected_fields: set[str],
    expected_schema: str,
    hash_field: str,
    run_id: str,
) -> None:
    if set(receipt) != expected_fields:
        raise P176RuntimeBridgeError("receipt_keyset_invalid")
    if receipt.get("schema_version") != expected_schema or receipt.get("phase") != "p176":
        raise P176RuntimeBridgeError("receipt_schema_invalid")
    if receipt.get("run_id") != run_id:
        raise P176RuntimeBridgeError("receipt_run_id_mismatch")
    expected_hash = stable_hash({key: value for key, value in receipt.items() if key != hash_field})
    if receipt.get(hash_field) != expected_hash:
        raise P176RuntimeBridgeError("receipt_self_hash_invalid")


def _verify_artifact_hashes(
    directory: Path,
    actual: Any,
    paths: Sequence[str],
    mismatch_error: str,
) -> None:
    if not isinstance(actual, dict) or set(actual) != set(paths):
        raise P176RuntimeBridgeError(mismatch_error)
    try:
        expected = _artifact_hashes(directory, paths)
    except (OSError, ValueError) as exc:
        raise P176RuntimeBridgeError(mismatch_error) from exc
    if actual != expected:
        raise P176RuntimeBridgeError(mismatch_error)


__all__ = [
    "BillingSnapshot",
    "COLLECTION_IN_PROGRESS_PATH",
    "COLLECTION_RECEIPT_PATH",
    "EPISODE_EVIDENCE_SOURCE_CLASSES",
    "EvidenceSnapshot",
    "FaultExecution",
    "FINALIZATION_RECEIPT_PATH",
    "HealthyObservation",
    "P176RuntimeArtifactProducer",
    "P176RuntimeBridgeError",
    "P176RuntimeConfig",
    "TeardownSnapshot",
    "fault_proof_hash",
]
