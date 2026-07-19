def changes($type; $name):
  [.resource_changes[] | select(.type == $type and .name == $name)];

def has_action($action): (.change.actions | index($action)) != null;
def after_project: .change.after.project? // "";
def after_project_id: .change.after.project_id? // "";
def forbidden_project:
  test("(prod|production|shared-vpc)");
def forbidden_member:
  (.change.after.member? // "") as $member
  | ($member == "allUsers" or $member == "allAuthenticatedUsers" or ($member | contains("*")));
def allowed_service:
  (.change.after.service? // "") as $service
  |
  ([
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudscheduler.googleapis.com",
    "compute.googleapis.com",
    "eventarc.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "oslogin.googleapis.com",
    "pubsub.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "workflows.googleapis.com"
  ] | index($service)) != null;
def allowed_admin_service:
  (.change.after.service? // "") as $service
  |
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
def allowed_lab_service:
  (.change.after.service? // "") as $service
  |
  ([
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
def source_contract:
  (.change.after.source_contents // "") as $source
  | ($source | contains("ifGenerationMatch: 0"))
  and ($source | contains("readLatestDurableState"))
  and ($source | contains("updateCanonicalLatestStateAtomically"))
  and ($source | contains("fail_closed_missing_budget_provider_state"))
  and ($source | contains("fail_closed_stale_budget_provider_state"))
  and ($source | contains("forecast_amount_krw * 1.15"))
  and ($source | contains("duplicate_terminal_success"))
  and ($source | contains("alreadyExists"))
  and ($source | contains("stop_compute_before_delete_project"))
  and ($source | contains("googleapis.compute.v1.instances.stop"))
  and ($source | contains("googleapis.cloudresourcemanager.v3.projects.delete"))
  and ($source | contains("name: ${\"projects/\" + lab_project_id}"))
  and (($source | index("googleapis.compute.v1.instances.stop")) < ($source | index("googleapis.cloudresourcemanager.v3.projects.delete")));
def budget_projects_are_lab:
  (.change.after.budget_filter[0].projects? // []) as $projects
  | (($projects | length) == 1 and ($projects[0] | startswith("projects/")))
    or (.change.after_unknown.budget_filter[0].projects == true);
def budget_pubsub_topic_is_admin_topic:
  (.change.after.all_updates_rule[0].pubsub_topic? // "") as $topic
  | ($topic == ("projects/" + $admin_project + "/topics/p176-cost-cutoff-budget"))
    or (.change.after_unknown.all_updates_rule[0].pubsub_topic == true);

(.variables.billing_account_id.value) as $billing_account
|
(.variables.region.value) as $region
|
(.variables.admin_project_id.value == $admin_project)
and (.variables.lab_project_id.value == $lab_project)
and (.variables.soft_stop_krw.value == 24000)
and (.variables.hard_cutoff_krw.value == 27000)
and (.variables.budget_krw.value == 30000)
and ($admin_project != $lab_project)
and ($admin_project | test("^opscat-p176-admin-[a-z0-9-]{6,20}$"))
and ($lab_project | test("^opscat-p176-live-[a-z0-9-]{6,20}$"))
and ([.resource_changes[] | select(has_action("delete"))] | length) == 0
and all(.resource_changes[]; allowed_type(.type))
and ([.resource_changes[] | select(.type == "google_service_account_key"
  or .type == "google_compute_shared_vpc_host_project"
  or .type == "google_compute_shared_vpc_service_project")] | length) == 0
and ([.resource_changes[] | select((after_project | forbidden_project) or (after_project_id | forbidden_project) or forbidden_member)] | length) == 0
and ([.resource_changes[]
  | select((.type | startswith("google_organization_iam"))
    or (.type | startswith("google_folder_iam"))
    or .type == "google_project_iam_binding"
    or ((.type | startswith("google_project_iam")) and ((.change.after.role // "") == "roles/owner" or (.change.after.role // "") == "roles/editor")))] | length) == 0
and ([.resource_changes[]
  | select(.change.after.project? != null and (.change.after.project != $admin_project and .change.after.project != $lab_project))] | length) == 0
and ([.resource_changes[] | select(.type == "google_project")] | length) == 2
and (changes("google_project"; "admin")
  | map(select(.change.after.project_id == $admin_project
    and .change.after.name == $admin_project
    and (.change.after.org_id // "") != ""
    and .change.after.billing_account == ($billing_account)
    and .change.after.auto_create_network == false
    and .change.after.deletion_policy == "DELETE"))
  | length) == 1
and (changes("google_project"; "lab")
  | map(select(.change.after.project_id == $lab_project
    and .change.after.name == $lab_project
    and (.change.after.org_id // "") != ""
    and .change.after.billing_account == ($billing_account)
    and .change.after.auto_create_network == false
    and .change.after.deletion_policy == "DELETE"))
  | length) == 1
and (changes("google_project_service"; "admin")
  | map(select(.change.after.project == $admin_project and allowed_admin_service))
  | length) == 11
and (changes("google_project_service"; "lab")
  | map(select(.change.after.project == $lab_project and allowed_lab_service))
  | length) == 6
and ([.resource_changes[] | select(.type == "google_project_service" and (allowed_service | not))] | length) == 0
and (changes("google_monitoring_notification_channel"; "budget_email")
  | map(select(.change.after.project == $lab_project and .change.after.display_name == "P176 live budget email"))
  | length) == 1
	and (changes("google_billing_budget"; "lab")
	  | map(select((.change.after.billing_account == $billing_account or .change.after.billing_account == ("billingAccounts/" + $billing_account))
	    and budget_projects_are_lab
	    and .change.after.amount[0].specified_amount[0].currency_code == "KRW"
	    and .change.after.amount[0].specified_amount[0].units == "30000"
	    and budget_pubsub_topic_is_admin_topic
	    and .change.after.all_updates_rule[0].disable_default_iam_recipients == true))
	  | length) == 1
and (changes("google_pubsub_topic"; "budget_notifications")
  | map(select(.change.after.project == $admin_project and .change.after.name == "p176-cost-cutoff-budget"))
  | length) == 1
and (changes("google_eventarc_trigger"; "budget_to_workflow")
  | map(select(.change.after.project == $admin_project
    and (.change.after.name == "p176-cost-cutoff-budget-to-workflow"
      or .change.after.name == ("projects/" + $admin_project + "/locations/" + $region + "/triggers/p176-cost-cutoff-budget-to-workflow"))))
  | length) == 1
and (changes("google_storage_bucket"; "receipts")
  | map(select(.change.after.project == $admin_project
    and (.change.after.name | contains("p176-cost-cutoff-receipts"))
    and .change.after.uniform_bucket_level_access == true
    and .change.after.public_access_prevention == "enforced"))
  | length) == 1
and (changes("google_workflows_workflow"; "cutoff")
  | map(select(.change.after.project == $admin_project and .change.after.name == "p176-cost-cutoff" and source_contract))
  | length) == 1
and (changes("google_service_account"; "workflow")
  | map(select(.change.after.project == $admin_project and .change.after.account_id == "p176-cost-cutoff-workflow"))
  | length) == 1
and (changes("google_project_iam_custom_role"; "lab_controller")
  | map(select(.change.after.project == $lab_project
    and .change.after.role_id == "p176CostCutoffLabController"
    and ((.change.after.permissions | sort) == ([
      "compute.instances.get",
      "compute.instances.list",
      "compute.instances.stop",
      "compute.zoneOperations.get",
      "resourcemanager.projects.delete",
      "resourcemanager.projects.get"
    ] | sort))))
  | length) == 1
