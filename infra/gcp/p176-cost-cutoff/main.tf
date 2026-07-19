locals {
  # Policy contract text for static guards: non-lab admin project, reject lab-hosted controller,
  # production, shared-vpc, wildcard IAM, owner/editor, service account keys, and OpsCat mutation grants.
  labels = {
    purpose    = "p176-cost-cutoff"
    owner      = "kdh"
    ticket     = "p176"
    controller = "out-of-band"
  }

  required_admin_services = toset([
    "cloudbilling.googleapis.com",
    "cloudscheduler.googleapis.com",
    "compute.googleapis.com",
    "eventarc.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "pubsub.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "workflows.googleapis.com",
  ])

  required_lab_services = toset([
    "billingbudgets.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "oslogin.googleapis.com",
  ])

  budget_notification_publisher_member = "serviceAccount:${join("@", ["billing-budget-notifications", "system.gserviceaccount.com"])}"

  workflow_source = <<-YAML
    main:
      params: [event]
      steps:
        - init:
            assign:
              - admin_project_id: ${var.admin_project_id}
              - lab_project_id: ${var.lab_project_id}
              - billing_account_id: ${var.billing_account_id}
              - receipt_bucket: ${google_storage_bucket.receipts.name}
              - soft_stop_krw: ${var.soft_stop_krw}
              - hard_cutoff_krw: ${var.hard_cutoff_krw}
              - budget_krw: ${var.budget_krw}
              - stale_after_seconds: ${var.stale_after_seconds}
              - terminal_ttl_seconds: ${var.terminal_ttl_seconds}
              - absolute_lease_seconds: ${var.absolute_lease_seconds}
              - now_epoch: $${sys.now()}
              - now: $${time.format(now_epoch)}
              - notification_time: $${default(map.get(event, "time"), now)}
              - notification_age_seconds: $${now_epoch - time.parse(notification_time)}
              - payload: $${default(map.get(event, "data"), {})}
              - trigger_kind: $${default(map.get(payload, "triggerKind"), "budget_event")}
              - state_object: "state/latest.json"
              - provider_receipt_object: $${"state/provider-" + now + ".json"}
              - budget_payload: null
              - cost_amount: null
              - budget_amount: null
              - currency_code: null
              - forecast_value: null
              - forecast_available: false
              - actual_amount_krw: null
              - budget_amount_krw: null
              - forecast_amount_krw: null
              - forecast_with_margin_krw: null
              - forecast_amount_krw_metadata: "unavailable"
              - forecast_with_margin_krw_metadata: "unavailable"
              - effective_amount_krw: null
              - observed_at: $${notification_time}
              - threshold_basis: "PROVIDER_ACTUAL"
              - duplicate_retry: false
              - terminal_success: false
              - terminal_generation: "0"
        - schedulerMustUseDurableState:
            switch:
              - condition: $${trigger_kind == "timer"}
                steps:
                  - readLatestDurableState:
                      try:
                        call: googleapis.storage.v1.objects.get
                        args:
                          bucket: $${receipt_bucket}
                          object: $${state_object}
                        result: latest_state
                      except:
                        as: missingLatestState
                        steps:
                          - hardStopMissingState:
                              return:
                                status: fail_closed_missing_budget_provider_state
                                reason: timer_requires_last_durable_budget_provider_state
                                missingLatestState: $${missingLatestState}
                  - loadLatestDurableState:
                      assign:
                        - actual_amount_krw: $${double(map.get(latest_state.metadata, "actual_amount_krw"))}
                        - budget_amount_krw: $${double(map.get(latest_state.metadata, "budget_amount_krw"))}
                        - forecast_amount_krw_metadata: $${default(map.get(latest_state.metadata, "forecast_amount_krw"), "unavailable")}
                        - forecast_with_margin_krw_metadata: $${default(map.get(latest_state.metadata, "forecast_with_margin_krw"), "unavailable")}
                        - forecast_available: $${default(map.get(latest_state.metadata, "forecast_available"), "false") == "true"}
                        - effective_amount_krw: $${double(map.get(latest_state.metadata, "effective_amount_krw"))}
                        - observed_at: $${default(map.get(latest_state.metadata, "observed_at"), "")}
                        - threshold_basis: $${default(map.get(latest_state.metadata, "threshold_basis"), "DURABLE_STATE")}
                  - hardStopStaleDurableState:
                      switch:
                        - condition: $${observed_at == ""}
                          return:
                            status: fail_closed_stale_budget_provider_state
                            stale_after_seconds: $${stale_after_seconds}
                            observed_at: $${observed_at}
                        - condition: $${now_epoch - time.parse(observed_at) > stale_after_seconds}
                          return:
                            status: fail_closed_stale_budget_provider_state
                            stale_after_seconds: $${stale_after_seconds}
                            observed_at: $${observed_at}
              - condition: $${trigger_kind != "timer"}
                steps:
                  - decodeBudgetPubsubCloudEvent:
                      try:
                        steps:
                          - loadPubsubMessageData:
                              assign:
                                - pubsub_message_data: $${event.data.message.data}
                          - parseBudgetMessageData:
                              assign:
                                - budget_payload: $${json.decode(base64.decode(pubsub_message_data))}
                      except:
                        as: malformedBudgetEvent
                        steps:
                          - rejectMalformedBudgetEvent:
                              return:
                                status: malformed_budget_event
                                reason: eventarc_pubsub_message_data_must_be_base64_json
                                malformedBudgetEvent: $${malformedBudgetEvent}
                  - rejectStaleBudgetEvent:
                      switch:
                        - condition: $${notification_age_seconds > stale_after_seconds}
                          return:
                            status: stale
                            stale_after_seconds: $${stale_after_seconds}
                            notification_age_seconds: $${notification_age_seconds}
                  - rejectNonObjectBudgetPayload:
                      switch:
                        - condition: $${get_type(budget_payload) != "map"}
                          return:
                            status: malformed_budget_event
                            reason: budget_message_data_must_decode_to_json_object
                  - loadRequiredBudgetFields:
                      assign:
                        - cost_amount: $${map.get(budget_payload, "costAmount")}
                        - budget_amount: $${map.get(budget_payload, "budgetAmount")}
                        - currency_code: $${map.get(budget_payload, "currencyCode")}
                        - forecast_value: $${map.get(budget_payload, "forecastAmount")}
                  - validateRequiredBudgetFields:
                      switch:
                        - condition: $${cost_amount == null}
                          return:
                            status: malformed_budget_event
                            reason: missing_costAmount
                        - condition: $${budget_amount == null}
                          return:
                            status: malformed_budget_event
                            reason: missing_budgetAmount
                        - condition: $${currency_code == null}
                          return:
                            status: malformed_budget_event
                            reason: missing_currencyCode
                        - condition: $${get_type(cost_amount) != "integer" and get_type(cost_amount) != "double"}
                          return:
                            status: malformed_budget_event
                            reason: costAmount_must_be_numeric
                        - condition: $${get_type(budget_amount) != "integer" and get_type(budget_amount) != "double"}
                          return:
                            status: malformed_budget_event
                            reason: budgetAmount_must_be_numeric
                        - condition: $${get_type(currency_code) != "string"}
                          return:
                            status: malformed_budget_event
                            reason: currencyCode_must_be_string
                        - condition: $${cost_amount < 0}
                          return:
                            status: malformed_budget_event
                            reason: costAmount_must_be_nonnegative
                        - condition: $${budget_amount < 0}
                          return:
                            status: malformed_budget_event
                            reason: budgetAmount_must_be_nonnegative
                        - condition: $${currency_code != "KRW"}
                          return:
                            status: wrong_currency
                            expected_currency: KRW
                            currencyCode: $${currency_code}
                  - validateOptionalForecastAmount:
                      switch:
                        - condition: $${forecast_value != null and get_type(forecast_value) != "integer" and get_type(forecast_value) != "double"}
                          return:
                            status: malformed_budget_event
                            reason: forecastAmount_must_be_numeric_when_present
                        - condition: $${forecast_value != null and forecast_value < 0}
                          return:
                            status: malformed_budget_event
                            reason: forecastAmount_must_be_nonnegative_when_present
                  - loadBudgetProviderState:
                      assign:
                        - actual_amount_krw: $${double(cost_amount)}
                        - budget_amount_krw: $${double(budget_amount)}
                        - effective_amount_krw: $${double(cost_amount)}
                        - observed_at: $${notification_time}
                  - loadOptionalForecastState:
                      switch:
                        - condition: $${forecast_value != null}
                          steps:
                            - calculateForecastState:
                                assign:
                                  - forecast_available: true
                                  - forecast_amount_krw: $${double(forecast_value)}
                                  - forecast_with_margin_krw: $${forecast_amount_krw * 1.15}
                                  - forecast_amount_krw_metadata: $${string(forecast_amount_krw)}
                                  - forecast_with_margin_krw_metadata: $${string(forecast_with_margin_krw)}
                                  - effective_amount_krw: $${if(actual_amount_krw >= forecast_with_margin_krw, actual_amount_krw, forecast_with_margin_krw)}
                  - writeProviderStateReceipt:
                      call: googleapis.storage.v1.objects.insert
                      args:
                        bucket: $${receipt_bucket}
                        ifGenerationMatch: 0
                        name: $${provider_receipt_object}
                        body:
                          contentType: application/json
                          metadata:
                            receipt_type: budget_provider_state
                            lab_project_id: $${lab_project_id}
                            observed_at: $${observed_at}
                            actual_amount_krw: $${string(actual_amount_krw)}
                            budget_amount_krw: $${string(budget_amount_krw)}
                            currency_code: $${currency_code}
                            forecast_amount_krw: $${forecast_amount_krw_metadata}
                            forecast_with_margin_krw: $${forecast_with_margin_krw_metadata}
                            forecast_available: $${string(forecast_available)}
                            effective_amount_krw: $${string(effective_amount_krw)}
                            threshold_basis: $${threshold_basis}
                  - readLatestGeneration:
                      try:
                        call: googleapis.storage.v1.objects.get
                        args:
                          bucket: $${receipt_bucket}
                          object: $${state_object}
                        result: existing_latest_state
                      except:
                        as: latestMissing
                        steps:
                          - initializeLatestGeneration:
                              assign:
                                - existing_latest_state:
                                    generation: "0"
                  - updateCanonicalLatestStateAtomically:
                      call: googleapis.storage.v1.objects.insert
                      args:
                        bucket: $${receipt_bucket}
                        ifGenerationMatch: $${int(existing_latest_state.generation)}
                        name: $${state_object}
                        body:
                          contentType: application/json
                          metadata:
                            receipt_type: canonical_latest_budget_provider_state
                            provider_receipt_object: $${provider_receipt_object}
                            lab_project_id: $${lab_project_id}
                            observed_at: $${observed_at}
                            actual_amount_krw: $${string(actual_amount_krw)}
                            budget_amount_krw: $${string(budget_amount_krw)}
                            currency_code: $${currency_code}
                            forecast_amount_krw: $${forecast_amount_krw_metadata}
                            forecast_with_margin_krw: $${forecast_with_margin_krw_metadata}
                            forecast_available: $${string(forecast_available)}
                            effective_amount_krw: $${string(effective_amount_krw)}
                            threshold_basis: $${threshold_basis}
        - prepareDedupe:
            assign:
              - dedupe_key: $${lab_project_id + "-" + trigger_kind + "-" + string(effective_amount_krw) + "-" + threshold_basis + "-" + observed_at}
              - lease_object: $${"leases/" + dedupe_key + ".json"}
              - terminal_object: $${"terminal/" + dedupe_key + ".json"}
        - createDurableLease:
            try:
              call: googleapis.storage.v1.objects.insert
              args:
                bucket: $${receipt_bucket}
                ifGenerationMatch: 0
                name: $${lease_object}
                body:
                  contentType: application/json
                  metadata:
                    absolute_lease_seconds: $${string(absolute_lease_seconds)}
                    terminal_ttl_seconds: $${string(terminal_ttl_seconds)}
                    lab_project_id: $${lab_project_id}
                    status: in_progress
            except:
              as: alreadyExists
              steps:
                - inspectTerminalReceiptForDuplicate:
                    try:
                      call: googleapis.storage.v1.objects.get
                      args:
                        bucket: $${receipt_bucket}
                        object: $${terminal_object}
                      result: existing_terminal_receipt
                    except:
                      as: missingTerminalReceipt
                      steps:
                        - markDuplicateRetry:
                            assign:
                              - duplicate_retry: true
                              - existing_terminal_receipt:
                                  generation: "0"
                                  metadata:
                                    terminal_success: "false"
                - captureTerminalReceiptGeneration:
                    assign:
                      - terminal_generation: $${default(map.get(existing_terminal_receipt, "generation"), "0")}
                - duplicateTerminalSuccessReturn:
                    switch:
                      - condition: $${default(map.get(existing_terminal_receipt.metadata, "terminal_success"), "false") == "true"}
                        return:
                          status: duplicate_terminal_success
                          idempotency: terminal_receipt_success
                          terminal_object: $${terminal_object}
                - retryDuplicateNonTerminal:
                    assign:
                      - duplicate_retry: true
        - belowSoftStop:
            switch:
              - condition: $${effective_amount_krw < soft_stop_krw}
                return:
                  status: observe_only
                  budget_krw: $${budget_krw}
                  actual_amount_krw: $${actual_amount_krw}
                  forecast_amount_krw: $${forecast_amount_krw}
                  effective_amount_krw: $${effective_amount_krw}
        - stop_compute_before_disable_billing:
            call: googleapis.compute.v1.instances.aggregatedList
            args:
              project: $${lab_project_id}
            result: aggregated_instances
        - stopEachZone:
            for:
              value: zone_entry
              in: $${keys(default(map.get(aggregated_instances, "items"), {}))}
              steps:
                - stopEachInstance:
                    for:
                      value: instance
                      in: $${default(map.get(aggregated_instances.items[zone_entry], "instances"), [])}
                      steps:
                        - stopInstance:
                            call: googleapis.compute.v1.instances.stop
                            args:
                              project: $${lab_project_id}
                              zone: $${text.split(zone_entry, "/")[1]}
                              instance: $${instance.name}
        - hardCutoff:
            switch:
              - condition: $${effective_amount_krw >= hard_cutoff_krw}
                steps:
                  - disableBillingAfterComputeStop:
                      call: googleapis.cloudbilling.v1.projects.updateBillingInfo
                      args:
                        name: $${"projects/" + lab_project_id}
                        body:
                          billingAccountName: null
        - writeTerminalReceipt:
            call: googleapis.storage.v1.objects.insert
            args:
              bucket: $${receipt_bucket}
              ifGenerationMatch: $${int(terminal_generation)}
              name: $${terminal_object}
              body:
                contentType: application/json
                metadata:
                  terminal_ttl_seconds: $${string(terminal_ttl_seconds)}
                  status: $${if(effective_amount_krw >= hard_cutoff_krw, "hard_cutoff", "soft_stop")}
                  terminal_success: "true"
                  duplicate_retry: $${string(duplicate_retry)}
                  actual_amount_krw: $${string(actual_amount_krw)}
                  budget_amount_krw: $${string(budget_amount_krw)}
                  forecast_amount_krw: $${forecast_amount_krw_metadata}
                  forecast_with_margin_krw: $${forecast_with_margin_krw_metadata}
                  forecast_available: $${string(forecast_available)}
                  effective_amount_krw: $${string(effective_amount_krw)}
        - done:
            return:
              status: $${if(effective_amount_krw >= hard_cutoff_krw, "hard_cutoff", "soft_stop")}
              ordering: stop_compute_before_disable_billing
              budget_krw: $${budget_krw}
              soft_stop_krw: $${soft_stop_krw}
              hard_cutoff_krw: $${hard_cutoff_krw}
              actual_amount_krw: $${actual_amount_krw}
              forecast_amount_krw: $${forecast_amount_krw}
              effective_amount_krw: $${effective_amount_krw}
  YAML
}

check "admin_and_lab_projects_are_separate" {
  assert {
    condition     = var.admin_project_id != var.lab_project_id
    error_message = "P176 cost cutoff admin project and lab project must be separate."
  }
}

resource "google_project" "admin" {
  name                = var.admin_project_id
  project_id          = var.admin_project_id
  org_id              = var.org_id
  billing_account     = var.billing_account_id
  auto_create_network = false
  deletion_policy     = "DELETE"
  labels              = local.labels
}

resource "google_project" "lab" {
  name                = var.lab_project_id
  project_id          = var.lab_project_id
  org_id              = var.org_id
  billing_account     = var.billing_account_id
  auto_create_network = false
  deletion_policy     = "DELETE"
  labels              = merge(local.labels, { controller = "lab" })
}

resource "google_project_service" "admin" {
  for_each = local.required_admin_services

  project            = google_project.admin.project_id
  service            = each.value
  disable_on_destroy = false

  depends_on = [google_project.admin]
}

resource "google_project_service" "lab" {
  for_each = local.required_lab_services

  project            = google_project.lab.project_id
  service            = each.value
  disable_on_destroy = false

  depends_on = [google_project.lab]
}

resource "google_service_account" "workflow" {
  project      = google_project.admin.project_id
  account_id   = "p176-cost-cutoff-workflow"
  display_name = "P176 cost cutoff workflow controller"

  depends_on = [google_project_service.admin]
}

resource "google_service_account" "eventarc" {
  project      = google_project.admin.project_id
  account_id   = "p176-cost-cutoff-eventarc"
  display_name = "P176 cost cutoff Eventarc trigger"

  depends_on = [google_project_service.admin]
}

resource "google_service_account" "scheduler" {
  project      = google_project.admin.project_id
  account_id   = "p176-cost-cutoff-scheduler"
  display_name = "P176 cost cutoff 5-minute scheduler fallback"

  depends_on = [google_project_service.admin]
}

resource "google_pubsub_topic" "budget_notifications" {
  project = google_project.admin.project_id
  name    = "p176-cost-cutoff-budget"
  labels  = local.labels

  depends_on = [google_project_service.admin]
}

resource "google_pubsub_topic_iam_member" "budget_notifications_publisher" {
  project = google_project.admin.project_id
  topic   = google_pubsub_topic.budget_notifications.name
  role    = "roles/pubsub.publisher"
  member  = local.budget_notification_publisher_member
}

resource "google_monitoring_notification_channel" "budget_email" {
  project      = google_project.lab.project_id
  display_name = "P176 live budget email"
  type         = "email"
  labels = {
    email_address = var.budget_alert_email
  }
  user_labels = local.labels

  depends_on = [google_project_service.lab]
}

resource "google_billing_budget" "lab" {
  provider        = google.p176_cost_quota
  billing_account = var.billing_account_id
  display_name    = "P176 disposable live lab budget"

  budget_filter {
    projects = ["projects/${google_project.lab.number}"]
  }

  amount {
    specified_amount {
      currency_code = "KRW"
      units         = tostring(var.budget_krw)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.75
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.budget_email.id]
    pubsub_topic                     = google_pubsub_topic.budget_notifications.id
    disable_default_iam_recipients   = true
  }
}

resource "google_storage_bucket" "receipts" {
  project                     = google_project.admin.project_id
  name                        = "${var.admin_project_id}-p176-cost-cutoff-receipts"
  location                    = var.region
  labels                      = local.labels
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  retention_policy {
    retention_period = var.absolute_lease_seconds
    is_locked        = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }

    condition {
      age        = 2
      with_state = "ANY"
    }
  }

  depends_on = [google_project_service.admin]
}

resource "google_storage_bucket_iam_member" "workflow_receipt_creator" {
  bucket = google_storage_bucket.receipts.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.workflow.email}"
}

resource "google_storage_bucket_iam_member" "workflow_receipt_viewer" {
  bucket = google_storage_bucket.receipts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.workflow.email}"
}

resource "google_project_iam_member" "workflow_log_writer" {
  project = google_project.admin.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.workflow.email}"
}

resource "google_project_iam_member" "eventarc_event_receiver" {
  project = google_project.admin.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.eventarc.email}"
}

resource "google_project_iam_custom_role" "lab_controller" {
  project     = google_project.lab.project_id
  role_id     = "p176CostCutoffLabController"
  title       = "P176 Cost Cutoff Lab Controller"
  description = "Exact P176 cost cutoff permissions for the disposable lab project only."
  permissions = [
    "billing.resourceAssociations.delete",
    "billing.resourceAssociations.get",
    "compute.instances.get",
    "compute.instances.list",
    "compute.instances.stop",
    "compute.zoneOperations.get",
    "resourcemanager.projects.get",
  ]

  depends_on = [google_project_service.lab]
}

resource "google_project_iam_member" "workflow_lab_controller" {
  project = google_project.lab.project_id
  role    = google_project_iam_custom_role.lab_controller.id
  member  = "serviceAccount:${google_service_account.workflow.email}"
}

resource "google_workflows_workflow" "cutoff" {
  project         = google_project.admin.project_id
  name            = "p176-cost-cutoff"
  region          = var.region
  description     = "Out-of-band P176 cost cutoff control plane; stop compute before disabling billing."
  service_account = google_service_account.workflow.id
  labels          = local.labels
  source_contents = local.workflow_source

  depends_on = [
    google_project_service.admin,
    google_project_iam_member.workflow_lab_controller,
    google_storage_bucket_iam_member.workflow_receipt_creator,
    google_storage_bucket_iam_member.workflow_receipt_viewer,
  ]
}

resource "google_project_iam_member" "eventarc_workflows_invoker" {
  project = google_project.admin.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.eventarc.email}"
}

resource "google_project_iam_member" "scheduler_workflows_invoker" {
  project = google_project.admin.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_eventarc_trigger" "budget_to_workflow" {
  project         = google_project.admin.project_id
  name            = "p176-cost-cutoff-budget-to-workflow"
  location        = var.region
  service_account = google_service_account.eventarc.email
  labels          = local.labels

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.budget_notifications.id
    }
  }

  destination {
    workflow = google_workflows_workflow.cutoff.name
  }

  depends_on = [
    google_project_service.admin,
    google_project_iam_member.eventarc_event_receiver,
    google_project_iam_member.eventarc_workflows_invoker,
  ]
}

resource "google_cloud_scheduler_job" "fallback_probe" {
  project     = google_project.admin.project_id
  name        = "p176-cost-cutoff-fallback"
  region      = var.region
  description = "5-minute fail-closed fallback invocation for P176 cost cutoff."
  schedule    = "*/5 * * * *"
  time_zone   = var.scheduler_time_zone

  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/${google_workflows_workflow.cutoff.id}/executions"
    body = base64encode(jsonencode({
      argument = jsonencode({
        data = {
          triggerKind    = "timer"
          thresholdBasis = "DURABLE_STATE_TIMER"
        }
      })
    }))

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.admin,
    google_project_iam_member.scheduler_workflows_invoker,
  ]
}
