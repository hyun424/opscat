def changes($type; $name):
  [.resource_changes[] | select(.type == $type and .name == $name)];

(.variables.billing_account_id.value) as $billing
| (.variables.cost_cutoff_budget_topic_name.value | test("^projects/opscat-p176-admin-[a-z0-9-]{6,20}/topics/p176-cost-cutoff-budget$"))
and (.variables.project_id.value == $project)
and (.variables.billing_account_id.value == $billing)
and ([.resource_changes[]
  | select(.type == "google_project"
    or .type == "google_project_service"
    or .type == "google_billing_budget"
    or .type == "google_monitoring_notification_channel"
    or .type == "google_billing_project_info")] | length) == 0
and ([.resource_changes[]
  | select((.change.actions | index("delete")) != null)] | length) == 0
and ([.resource_changes[]
  | select(.change.after.project? != null and .change.after.project != $project)] | length) == 0
and ([.resource_changes[]
  | select(.type == "google_compute_network" and .change.after.name == "default")] | length) == 0
and ([.resource_changes[]
  | select(.type == "google_compute_instance" and (.change.after.network_interface[]?.access_config? | length) > 0)] | length) == 0
and ([.resource_changes[]
  | select(.type == "google_compute_address")] | length) == 0
and (changes("google_compute_router"; "p176_live")
  | map(select(.change.after.project == $project
    and .change.after.name == "p176-live-router"
    and .change.after.region == "asia-northeast3"))
  | length) == 1
and (changes("google_compute_router_nat"; "p176_live")
  | map(select(.change.after.project == $project
    and .change.after.name == "p176-live-nat"
    and .change.after.nat_ip_allocate_option == "AUTO_ONLY"
    and .change.after.source_subnetwork_ip_ranges_to_nat == "LIST_OF_SUBNETWORKS"
    and ((.change.after.subnetwork // []) | length) == 1
    and ((.change.after.subnetwork[0].name) as $subnetwork_name
      | (($subnetwork_name | type) == "string"
        and ($subnetwork_name == "p176-live-subnet"
          or ($subnetwork_name | endswith("/regions/asia-northeast3/subnetworks/p176-live-subnet"))))
        or .change.after_unknown.subnetwork[0].name == true)
    and .change.after.subnetwork[0].source_ip_ranges_to_nat == ["ALL_IP_RANGES"]))
  | length) == 1
and ([.resource_changes[]
  | select(.type == "google_compute_firewall" and .change.after.direction == "INGRESS")] as $ingress
  | ($ingress | length) == 2
    and ([$ingress[] | select(.name == "iap_ssh"
      and .change.after.name == "p176-live-iap-ssh"
      and .change.after.project == $project
      and .change.after.priority == 1000
      and .change.after.source_ranges == ["35.235.240.0/20"]
      and ((.change.after.source_tags // []) | length) == 0
      and (.change.after.target_tags | sort) == ["opscat-p176-live-observer", "opscat-p176-live-target"]
      and ((.change.after.allow // []) | length) == 1
      and any(.change.after.allow[]; .protocol == "tcp" and .ports == ["22"])
      and ((.change.after.deny // []) | length) == 0)] | length) == 1
    and ([$ingress[] | select(.name == "observer_to_target_private"
      and .change.after.name == "p176-live-observer-to-target-private"
      and .change.after.project == $project
      and .change.after.priority == 1000
      and ((.change.after.source_ranges // []) | length) == 0
      and .change.after.source_tags == ["opscat-p176-live-observer"]
      and .change.after.target_tags == ["opscat-p176-live-target"]
      and ((.change.after.allow // []) | length) == 1
      and any(.change.after.allow[]; .protocol == "tcp" and .ports == ["8000"])
      and ((.change.after.deny // []) | length) == 0)] | length) == 1)
and ([.resource_changes[]
  | select(.type == "google_compute_firewall" and .change.after.direction == "EGRESS")] as $egress
  | ($egress | length) == 3
    and ([$egress[] | select(.name == "observer_to_target_private_egress"
      and .change.after.name == "p176-live-observer-to-target-private-egress"
      and .change.after.project == $project
      and .change.after.priority == 900
      and .change.after.destination_ranges == ["10.176.0.10/32"]
      and .change.after.target_tags == ["opscat-p176-live-observer"]
      and ((.change.after.allow // []) | length) == 1
      and any(.change.after.allow[]; .protocol == "tcp" and .ports == ["8000"])
      and ((.change.after.deny // []) | length) == 0)] | length) == 1
    and ([$egress[] | select(.name == "bounded_web_dns_egress"
      and .change.after.name == "p176-live-bounded-web-dns-egress"
      and .change.after.project == $project
      and .change.after.priority == 1000
      and .change.after.destination_ranges == ["0.0.0.0/0"]
      and (.change.after.target_tags | sort) == ["opscat-p176-live-observer", "opscat-p176-live-target"]
      and ((.change.after.allow // []) | length) == 2
      and any(.change.after.allow[]; .protocol == "tcp" and (.ports | sort) == ["443", "53", "80"])
      and any(.change.after.allow[]; .protocol == "udp" and .ports == ["53"])
      and ((.change.after.deny // []) | length) == 0)] | length) == 1
    and ([$egress[] | select(.name == "deny_other_egress"
      and .change.after.name == "p176-live-deny-other-egress"
      and .change.after.project == $project
      and .change.after.priority == 1100
      and .change.after.destination_ranges == ["0.0.0.0/0"]
      and (.change.after.target_tags | sort) == ["opscat-p176-live-observer", "opscat-p176-live-target"]
      and ((.change.after.allow // []) | length) == 0
      and ((.change.after.deny // []) | length) == 1
      and any(.change.after.deny[]; .protocol == "all"))] | length) == 1)
and ([.resource_changes[]
  | select(.type == "google_service_account_key")] | length) == 0
and ([.resource_changes[]
  | select(.type == "google_project_iam_member"
    and (.name | startswith("opscat")))] | length) == 0
