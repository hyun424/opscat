def has_action($action): (.change.actions | index($action)) != null;
def before_project: .change.before.project? // "";
def before_project_id: .change.before.project_id? // "";
def allowed_admin_service($service):
  ([
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudscheduler.googleapis.com",
    "compute.googleapis.com",
    "eventarc.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "pubsub.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "workflows.googleapis.com"
  ] | index($service)) != null;
def allowed_lab_service($service):
  ([
    "billingbudgets.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "oslogin.googleapis.com"
  ] | index($service)) != null;
def allowed_type($type):
  ([
    "google_cloud_scheduler_job",
    "google_eventarc_trigger",
    "google_billing_budget",
    "google_monitoring_notification_channel",
    "google_project",
    "google_project_iam_custom_role",
    "google_project_iam_member",
    "google_project_service",
    "google_pubsub_topic",
    "google_pubsub_topic_iam_member",
    "google_service_account",
    "google_storage_bucket",
    "google_storage_bucket_iam_member",
    "google_workflows_workflow"
  ] | index($type)) != null;
def module_owned_address_name:
  (.type == "google_project" and .name == "admin" and .address == "google_project.admin")
  or (.type == "google_project" and .name == "lab" and .address == "google_project.lab")
  or (.type == "google_project_service" and .name == "admin"
    and (.address | test("^google_project_service\\.admin\\[\"[a-z0-9.-]+\"\\]$"))
    and allowed_admin_service(.change.before.service))
  or (.type == "google_project_service" and .name == "lab"
    and (.address | test("^google_project_service\\.lab\\[\"[a-z0-9.-]+\"\\]$"))
    and allowed_lab_service(.change.before.service))
  or (.type == "google_service_account" and .name == "workflow" and .address == "google_service_account.workflow")
  or (.type == "google_service_account" and .name == "eventarc" and .address == "google_service_account.eventarc")
  or (.type == "google_service_account" and .name == "scheduler" and .address == "google_service_account.scheduler")
  or (.type == "google_pubsub_topic" and .name == "budget_notifications" and .address == "google_pubsub_topic.budget_notifications")
  or (.type == "google_pubsub_topic_iam_member" and .name == "budget_notifications_publisher" and .address == "google_pubsub_topic_iam_member.budget_notifications_publisher")
  or (.type == "google_monitoring_notification_channel" and .name == "budget_email" and .address == "google_monitoring_notification_channel.budget_email")
  or (.type == "google_billing_budget" and .name == "lab" and .address == "google_billing_budget.lab")
  or (.type == "google_storage_bucket" and .name == "receipts" and .address == "google_storage_bucket.receipts")
  or (.type == "google_storage_bucket_iam_member" and .name == "workflow_receipt_creator" and .address == "google_storage_bucket_iam_member.workflow_receipt_creator")
  or (.type == "google_storage_bucket_iam_member" and .name == "workflow_receipt_viewer" and .address == "google_storage_bucket_iam_member.workflow_receipt_viewer")
  or (.type == "google_project_iam_member" and .name == "workflow_log_writer" and .address == "google_project_iam_member.workflow_log_writer")
  or (.type == "google_project_iam_member" and .name == "eventarc_event_receiver" and .address == "google_project_iam_member.eventarc_event_receiver")
  or (.type == "google_project_iam_custom_role" and .name == "lab_controller" and .address == "google_project_iam_custom_role.lab_controller")
  or (.type == "google_project_iam_member" and .name == "workflow_lab_controller" and .address == "google_project_iam_member.workflow_lab_controller")
  or (.type == "google_workflows_workflow" and .name == "cutoff" and .address == "google_workflows_workflow.cutoff")
  or (.type == "google_project_iam_member" and .name == "eventarc_workflows_invoker" and .address == "google_project_iam_member.eventarc_workflows_invoker")
  or (.type == "google_project_iam_member" and .name == "scheduler_workflows_invoker" and .address == "google_project_iam_member.scheduler_workflows_invoker")
  or (.type == "google_eventarc_trigger" and .name == "budget_to_workflow" and .address == "google_eventarc_trigger.budget_to_workflow")
  or (.type == "google_cloud_scheduler_job" and .name == "fallback_probe" and .address == "google_cloud_scheduler_job.fallback_probe");

(.variables.billing_account_id.value) as $billing_account
|
([.resource_changes[] | select(.type == "google_project"
  and .name == "lab"
  and .address == "google_project.lab"
  and before_project_id == $lab_project)
  | (.change.before.number? // empty | tostring)] | unique) as $lab_project_numbers
|
($lab_project_numbers[0] // "") as $lab_project_number
|
(.variables.admin_project_id.value == $admin_project)
and (.variables.lab_project_id.value == $lab_project)
and ($lab_project_numbers | length) == 1
and ($lab_project_number | length) > 0
and ([.resource_changes[] | select(has_action("create") or has_action("update"))] | length) == 0
and ([.resource_changes[] | select(has_action("delete"))] | length) > 0
and ([.resource_changes[] | select(.type == "google_project" and .name == "admin"
  and before_project_id == $admin_project
  and .change.before.auto_create_network == false
  and .change.before.deletion_policy == "DELETE")] | length) == 1
and ([.resource_changes[] | select(.type == "google_project" and .name == "lab"
  and before_project_id == $lab_project
  and .change.before.auto_create_network == false
  and .change.before.deletion_policy == "DELETE")] | length) == 1
and ([.resource_changes[] | select(.type == "google_project")] | length) == 2
and all(.resource_changes[] | select(has_action("delete"));
  allowed_type(.type)
  and module_owned_address_name
  and (.change.after == null)
  and (if .type == "google_project"
       then (before_project_id == $admin_project or before_project_id == $lab_project)
       elif .type == "google_project_service" and .name == "lab"
       then before_project == $lab_project
       elif .type == "google_monitoring_notification_channel"
       then before_project == $lab_project
       elif .type == "google_billing_budget"
       then (.change.before.billing_account == $billing_account
         or .change.before.billing_account == ("billingAccounts/" + $billing_account))
         and .change.before.display_name == "P176 disposable live lab budget"
         and .change.before.budget_filter[0].projects == [("projects/" + $lab_project_number)]
       elif .type == "google_storage_bucket_iam_member"
       then ((.change.before.bucket == ($admin_project + "-p176-cost-cutoff-receipts"))
         or (.change.before.bucket == ("b/" + $admin_project + "-p176-cost-cutoff-receipts")))
         and .change.before.member == ("serviceAccount:p176-cost-cutoff-workflow@" + $admin_project + ".iam.gserviceaccount.com")
         and (if .name == "workflow_receipt_creator"
              then .change.before.role == "roles/storage.objectCreator"
              else .change.before.role == "roles/storage.objectViewer" end)
       elif .type == "google_project_iam_custom_role" or .name == "workflow_lab_controller"
       then before_project == $lab_project
       else before_project == $admin_project end))
