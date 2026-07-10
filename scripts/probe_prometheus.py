#!/usr/bin/env python3
"""Run one bounded Prometheus shadow probe; fixture mode is the default."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.connectors.base import ConnectorCallRequest  # noqa: E402
from app.connectors.prometheus import PrometheusReadOnlyConnector, parse_allowed_hosts  # noqa: E402
from app.services.redaction import redact_value  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Prometheus through OpsCat's read-only connector")
    parser.add_argument("--mode", choices=("fixture", "real"), default="fixture")
    parser.add_argument("--capability", choices=("health.check", "query.instant", "query.range"), default="query.instant")
    parser.add_argument("--query", default="up")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--step")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    settings = get_settings()
    connector = PrometheusReadOnlyConnector(
        base_url=settings.prometheus_base_url,
        allowed_hosts=parse_allowed_hosts(settings.prometheus_allowed_hosts),
        timeout_seconds=settings.prometheus_timeout_seconds,
    )
    payload = {"provider_mode": args.mode, "query": args.query}
    if args.capability == "query.range":
        payload.update({"start": args.start or "", "end": args.end or "", "step": args.step or ""})
    result = connector.call(
        ConnectorCallRequest(
            connector_id="prometheus.readonly",
            capability=args.capability,
            tenant_id="local",
            workspace_id="shadow",
            actor="prometheus-probe",
            payload=payload,
        )
    )
    result_payload = redact_value(asdict(result))
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"prometheus_probe ok={result.ok} mode={args.mode} capability={args.capability} network_attempted={result.output.get('network_attempted', False)}")
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
