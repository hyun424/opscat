def has_action($action): (.change.actions | index($action)) != null;

(.variables.project_id.value == $project)
and ([.resource_changes[]
  | select(.type == "google_project"
    or .type == "google_project_service"
    or .type == "google_billing_budget"
    or .type == "google_monitoring_notification_channel"
    or .type == "google_billing_project_info")] | length) == 0
and ([.resource_changes[]
  | select(has_action("create") or has_action("update"))] | length) == 0
and ([.resource_changes[]
  | select(has_action("delete"))] | length) > 0
and all(.resource_changes[] | select(has_action("delete"));
  (.type as $type
    | (["google_compute_network", "google_compute_subnetwork", "google_compute_firewall",
        "google_compute_router", "google_compute_router_nat",
        "google_compute_instance", "google_service_account", "google_project_iam_member",
        "google_project_iam_custom_role"]
       | index($type)) != null)
  and .change.before.project == $project)
