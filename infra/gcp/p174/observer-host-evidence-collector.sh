#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${P174_PROJECT_ID:?set P174_PROJECT_ID}"
ZONE="${P174_ZONE:?set P174_ZONE}"
TARGET_INSTANCE="${P174_TARGET_INSTANCE:?set P174_TARGET_INSTANCE}"
EVIDENCE_DIR="${P174_EVIDENCE_DIR:-/var/lib/opscat-p174/evidence}"
METADATA_ROOT="http://metadata.google.internal/computeMetadata/v1"
COMPUTE_ROOT="https://compute.googleapis.com/compute/v1"

case "${PROJECT_ID}" in
  opscat-p174-*) ;;
  *) echo "refusing non-P174 project: ${PROJECT_ID}" >&2; exit 1 ;;
esac
[[ "${ZONE}" == "asia-northeast3-a" ]] || { echo "refusing zone: ${ZONE}" >&2; exit 1; }
[[ "${TARGET_INSTANCE}" == "p174-target" ]] || { echo "refusing target instance: ${TARGET_INSTANCE}" >&2; exit 1; }

install -d -m 0750 -o root -g root "${EVIDENCE_DIR}"
tmp_body="$(mktemp /run/opscat-p174-compute-body.XXXXXX)"
tmp_headers="$(mktemp /run/opscat-p174-compute-headers.XXXXXX)"
cleanup() {
  rm -f "${tmp_body}" "${tmp_headers}"
}
trap cleanup EXIT

token="$(
  curl -fsS \
    -H "Metadata-Flavor: Google" \
    "${METADATA_ROOT}/instance/service-accounts/default/token" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)"

status_code="$(
  curl -sS \
    -o "${tmp_body}" \
    -D "${tmp_headers}" \
    -w "%{http_code}" \
    -H "Authorization: Bearer ${token}" \
    -H "Accept: application/json" \
    "${COMPUTE_ROOT}/projects/${PROJECT_ID}/zones/${ZONE}/instances/${TARGET_INSTANCE}" \
    || true
)"
unset token

body_sha256="$(shasum -a 256 "${tmp_body}" | awk '{print $1}')"
observed_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

python3 - "${tmp_body}" "${EVIDENCE_DIR}/compute-target-evidence.jsonl" "${observed_at}" "${status_code}" "${body_sha256}" "${PROJECT_ID}" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

body_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
observed_at = sys.argv[3]
status_code = int(sys.argv[4]) if sys.argv[4].isdigit() else 0
body_sha256 = sys.argv[5]
project_id = sys.argv[6]


def basename(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlparse(value)
    path = parsed.path if parsed.scheme else value
    return path.rstrip("/").rsplit("/", 1)[-1]


def hash_value(value: object) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def project_from_self_link(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parts = urlparse(value).path.split("/")
    try:
        return parts[parts.index("projects") + 1]
    except (ValueError, IndexError):
        return None


payload: dict[str, object]
try:
    raw = json.loads(body_path.read_text(encoding="utf-8") or "{}")
except json.JSONDecodeError:
    raw = {}

payload = {
    "schema_version": "p174.host_compute_evidence.v1",
    "observed_at": observed_at,
    "project_id": project_id,
    "self_link_project": project_from_self_link(raw.get("selfLink")),
    "http_status": status_code,
    "resource_body_sha256": body_sha256,
    "resource": {
        "name": raw.get("name"),
        "zone": basename(raw.get("zone")),
        "machine_type": basename(raw.get("machineType")),
        "status": raw.get("status"),
        "network_tags": sorted(raw.get("tags", {}).get("items", []))[:8],
        "label_keys": sorted((raw.get("labels") or {}).keys())[:16],
        "fingerprint_hash": hash_value(raw.get("fingerprint")),
        "label_fingerprint_hash": hash_value(raw.get("labelFingerprint")),
        "id_hash": hash_value(raw.get("id")),
    },
}

out_path.parent.mkdir(parents=True, exist_ok=True)
with out_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
PY
