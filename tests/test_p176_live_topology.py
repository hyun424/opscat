from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.p176_campaign import SERVICES, TELEMETRY_CLASSES

ROOT = Path(__file__).resolve().parents[1]
LIVE_LAB = ROOT / "lab/p176/live"
CANONICAL_SERVICE_IDS = [service["service_id"] for service in SERVICES]
SUPPORT_COMPONENTS = {
    "telemetry-collector",
    "fault-controller",
    "traffic-driver",
    "topology-exporter",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_p176_live_compose_has_exact_canonical_application_services_without_public_ingress() -> None:
    compose = _read_json(LIVE_LAB / "docker-compose.yml")
    services = compose["services"]

    assert [service for service in services if service in CANONICAL_SERVICE_IDS] == CANONICAL_SERVICE_IDS
    assert set(services) == set(CANONICAL_SERVICE_IDS) | SUPPORT_COMPONENTS

    for service_id in CANONICAL_SERVICE_IDS:
        service = services[service_id]
        assert "ports" not in service
        assert service["expose"]
        assert service["healthcheck"]["test"]
        assert service["read_only"] is True
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["cap_drop"] == ["ALL"]
        assert service["cpus"] > 0
        assert service["mem_limit"]
        assert service["pids_limit"] > 0
        assert service["labels"]["opscat.p176.live.role"] == "canonical-service"
        assert service["labels"]["opscat.p176.live.service_id"] == service_id


def test_p176_live_topology_freezes_dependency_criticality_and_ownership_from_campaign() -> None:
    topology = _read_json(LIVE_LAB / "topology.json")

    assert topology["schema_version"] == "p176.live_topology.v1"
    assert topology["service_order"] == CANONICAL_SERVICE_IDS
    assert topology["telemetry_classes"] == list(TELEMETRY_CLASSES)
    assert set(topology["support_components"]) == SUPPORT_COMPONENTS
    assert topology["public_application_ingress"] is False

    expected = {service["service_id"]: service for service in SERVICES}
    assert set(topology["services"]) == set(expected)
    for service_id, service in topology["services"].items():
        campaign_service = expected[service_id]
        assert service["depends_on"] == campaign_service["depends_on"]
        assert service["criticality_tier"] == campaign_service["criticality_tier"]
        assert service["ownership_domain"] == campaign_service["ownership_domain"]
        assert service["independently_deployable"] is True


def test_support_components_are_support_only_and_fault_controller_is_harness_only() -> None:
    compose = _read_json(LIVE_LAB / "docker-compose.yml")
    topology = _read_json(LIVE_LAB / "topology.json")

    for component_id in SUPPORT_COMPONENTS:
        component = compose["services"][component_id]
        assert component["labels"]["opscat.p176.live.role"] == "support-only"
        assert component["labels"]["opscat.p176.live.canonical_service"] == "false"
        assert component["read_only"] is True
        assert "ports" not in component
        assert component["healthcheck"]["test"]
        assert component["cpus"] > 0
        assert component["mem_limit"]
        assert component["pids_limit"] > 0

    fault_controller = topology["support_components"]["fault-controller"]
    assert fault_controller["mutation_authority"] == "harness-only"
    assert fault_controller["opscat_mutation_allowed"] is False
    assert fault_controller["cleanup_verb"] == "cleanup_fault_lease"
    assert len(fault_controller["allowed_fault_verbs"]) == 30
    assert all(verb.startswith("inject_") for verb in fault_controller["allowed_fault_verbs"])


def test_live_support_components_use_real_read_only_entrypoints_without_host_ports() -> None:
    compose = _read_json(LIVE_LAB / "docker-compose.yml")
    services = compose["services"]

    assert services["telemetry-collector"]["command"] == ["python", "/telemetry_collector.py"]
    assert services["fault-controller"]["command"] == ["python", "/fault_controller.py"]
    assert "./telemetry_collector.py:/telemetry_collector.py:ro" in services["telemetry-collector"]["volumes"]
    assert "./fault_controller.py:/fault_controller.py:ro" in services["fault-controller"]["volumes"]

    for component_id in ("telemetry-collector", "fault-controller"):
        component = services[component_id]
        assert "ports" not in component
        assert component["read_only"] is True
        assert component["cap_drop"] == ["ALL"]
        assert component["security_opt"] == ["no-new-privileges:true"]


def test_postgres_runs_unprivileged_with_ephemeral_writable_data_mount() -> None:
    compose = _read_json(LIVE_LAB / "docker-compose.yml")
    postgres = compose["services"]["postgres-db"]

    assert postgres["user"] == "70:70"
    assert "/var/lib/postgresql/data:size=512m,uid=70,gid=70,mode=0700" in postgres["tmpfs"]
    assert "volumes" not in postgres
    assert "volumes" not in compose


def test_runtime_bindings_are_private_and_observer_is_separate_from_target_workload() -> None:
    runtime = _read_json(LIVE_LAB / "docker-compose.runtime.yml")
    observer = _read_json(ROOT / "lab/p176/observer/docker-compose.yml")

    assert runtime["services"]["fault-controller"]["ports"] == ["10.176.0.10:8020:8091"]
    assert runtime["services"]["telemetry-collector"]["ports"] == ["10.176.0.10:8000:8090"]
    assert set(runtime["services"]) == {"fault-controller", "telemetry-collector"}

    observer_service = observer["services"]["observer-telemetry"]
    assert observer_service["ports"] == ["127.0.0.1:8030:8090"]
    assert observer_service["environment"]["P176_UPSTREAM_ENDPOINT"] == "http://10.176.0.10:8000"
    assert observer_service["read_only"] is True
    assert observer_service["cap_drop"] == ["ALL"]
    assert observer_service["security_opt"] == ["no-new-privileges:true"]
