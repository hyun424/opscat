from sqlalchemy.orm import Session

from app.models import Evidence, Incident

ERROR_CONTEXT = {
    "payment_api_deploy_regression": (
        "Sanitized error window: PaymentTimeoutError rose from 2/min to 180/min "
        "after deploy v1.42.0. Redacted request ids only; no raw cardholder data stored."
    ),
    "payment_bad_deploy": (
        "Sanitized error window: PaymentTimeoutError rose from 2/min to 180/min "
        "after deploy v1.42.0. Redacted request ids only; no raw cardholder data stored."
    ),
    "external_api_timeout": (
        "Sanitized dependency window: payment processor p95 latency rose to 9s while app error logs show upstream timeout codes."
    ),
    "worker_queue_backlog": (
        "Sanitized metric window: queue latency p95 increased to 12m after worker heartbeat degradation."
    ),
    "duplicate_alert_storm": (
        "Sanitized alert window: 42 duplicate fingerprints arrived after recovery metrics returned below threshold."
    ),
}

DEPLOY_CONTEXT = {
    "payment_api_deploy_regression": (
        "Deploy v1.42.0 by mock-ci changed payment-api DB pool timeout handling 8 minutes before alert."
    ),
    "payment_bad_deploy": (
        "Deploy v1.42.0 by mock-ci changed payment-api DB pool timeout handling 8 minutes before alert."
    ),
    "external_api_timeout": (
        "No payment-api deploy in the last 2h; dependency provider status is degraded in mock context."
    ),
    "worker_queue_backlog": (
        "No app deploy in last 2h; infra maintenance restarted queue broker 15 minutes before alert."
    ),
    "duplicate_alert_storm": (
        "No deploy or code change in last 4h; alert fingerprint matches resolved incident INC-2026-104."
    ),
}

RUNBOOKS = {
    "payment-api": {
        "owner": "payments-oncall",
        "known_causes": ["bad deploy", "upstream processor timeout", "DB pool exhaustion"],
        "safe_actions": ["mock.create_incident_ticket", "mock.create_rollback_pr"],
        "dangerous_actions": ["production rollback", "database mutation", "arbitrary shell execution"],
        "verification_checks": ["mock.verify_recovery", "error rate below threshold"],
    },
    "worker": {
        "owner": "platform-oncall",
        "known_causes": ["queue broker maintenance", "stuck worker", "poison message"],
        "safe_actions": ["mock.execute_restart_worker", "mock.create_incident_ticket"],
        "dangerous_actions": ["cloud deletion", "arbitrary shell execution"],
        "verification_checks": ["worker heartbeat is healthy", "queue latency decreases"],
    },
}

PRIORS = {
    "payment-api": (
        "Prior incident INC-2026-041: same PaymentTimeoutError after deploy; "
        "rollback PR resolved staging within 5 minutes."
    ),
    "worker": (
        "Prior incident INC-2026-088: queue broker maintenance caused transient "
        "worker lag; restart cleared non-prod backlog."
    ),
}


def _scenario(incident: Incident) -> str:
    return str(incident.alert_payload.get("scenario", "payment_api_deploy_regression"))


def _add_evidence(db: Session, incident: Incident, ev_type: str, content: str, metadata: dict[str, object]) -> Evidence:
    evidence = Evidence(
        incident_id=incident.id,
        type=ev_type,
        source="mock",
        source_url=f"mock://{ev_type}/{incident.service}",
        content=content,
        evidence_metadata=metadata,
    )
    db.add(evidence)
    db.flush()
    return evidence


def get_error_context(db: Session, incident: Incident) -> Evidence:
    scenario = _scenario(incident)
    return _add_evidence(
        db,
        incident,
        "log",
        ERROR_CONTEXT.get(scenario, ERROR_CONTEXT["payment_api_deploy_regression"]),
        {"tool": "mock.get_error_context", "redacted": True, "raw_log_storage": False},
    )


def get_recent_deploys(db: Session, incident: Incident) -> Evidence:
    scenario = _scenario(incident)
    return _add_evidence(
        db,
        incident,
        "deploy",
        DEPLOY_CONTEXT.get(scenario, DEPLOY_CONTEXT["payment_api_deploy_regression"]),
        {"tool": "mock.get_recent_deploys", "window_minutes": 60},
    )


def get_runbook(db: Session, incident: Incident) -> Evidence:
    runbook = RUNBOOKS.get(incident.service, RUNBOOKS["payment-api"])
    return _add_evidence(
        db,
        incident,
        "runbook",
        (
            f"Runbook for {incident.service}: owner={runbook['owner']}; "
            f"safe_actions={','.join(runbook['safe_actions'])}; "
            f"verification={','.join(runbook['verification_checks'])}"
        ),
        {"tool": "mock.get_runbook", "runbook": runbook},
    )


def search_prior_incidents(db: Session, incident: Incident) -> Evidence:
    return _add_evidence(
        db,
        incident,
        "prior_incident",
        PRIORS.get(incident.service, "No matching prior incidents found."),
        {"tool": "mock.search_prior_incidents", "memory_scope": incident.service},
    )


def gather_all_context(db: Session, incident: Incident) -> list[Evidence]:
    return [
        get_error_context(db, incident),
        get_recent_deploys(db, incident),
        get_runbook(db, incident),
        search_prior_incidents(db, incident),
    ]
