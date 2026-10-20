"""The IaC tables and iac addresses of the infra model — one copy, read by seed (drafting) and check (comparing).

Boundary §3 and §6 (docs/plans/2026-10-20-jui-viz-server-room-boundary.md). Ticket
2026-10-20-jui-infra-seed-and-check-tables-disagree: seed and check had each their own table and address forms, so a
draft seed wrote was warned about by check reading the same IaC. Everything that says what an IaC resource is lives
here: the provider of a Terraform type, the category and service of each type (Terraform, CloudFormation / SAM / CDK,
Bicep, Kubernetes, Compose images, wrangler bindings), the types that are parts of another resource (counted, never a
node), and the address a node's ``iac`` holds for each kind of input.

A mapping is (category, service); a category "group:<kind>" makes a group (a network, a cluster), not a node. The
categories IAM, policy and alarm (model.FOLDED_BY_DEFAULT) are mapped, not dropped: seed draws them folded, and check
compares them when the model declares them and says nothing when it does not (``optional``). Tables first written by
the seed lane (a verification subagent), moved here.
"""
from __future__ import annotations

import json
import re

from . import model as M

# Terraform: the provider of a resource type, by the type's prefix.
TF_PROVIDER = {"aws": "aws", "google": "gcp", "azurerm": "azure", "azuread": "azure", "cloudflare": "cloudflare",
               "vercel": "vercel", "digitalocean": "digitalocean", "heroku": "heroku", "kubernetes": "kubernetes",
               "helm": "kubernetes", "netlify": "netlify", "fly": "fly", "hcloud": "hetzner", "linode": "linode",
               "oci": "oracle", "alicloud": "alibaba", "mongodbatlas": "mongodb-atlas", "github": "github",
               "datadog": "datadog", "fastly": "fastly", "auth0": "auth0", "supabase": "supabase", "neon": "neon",
               "render": "render", "sentry": "sentry", "upstash": "upstash", "planetscale": "planetscale"}
TF_PROVIDER_BLOCK = {"google-beta": "gcp", "google": "gcp", "azurerm": "azure", "azuread": "azure"}
TF_UTILITY = {"random", "null", "local", "tls", "time", "archive", "external", "template", "http", "terraform",
              "cloudinit", "dns"}
TOP_GROUP_KIND = {"aws": "account", "gcp": "project", "azure": "subscription", "firebase": "project"}

# type -> (category, service); "group:<kind>" makes a group instead of a node.
TF_TYPES: dict[str, tuple[str, str]] = {
    # AWS
    "aws_instance": ("compute.vm", "ec2"), "aws_autoscaling_group": ("compute.vm", "ec2.asg"),
    "aws_ecs_service": ("compute.container", "ecs"), "aws_ecs_cluster": ("group:cluster", "ecs"),
    "aws_eks_cluster": ("compute.k8s", "eks"), "aws_lambda_function": ("compute.function", "lambda"),
    "aws_apprunner_service": ("compute.paas", "apprunner"),
    "aws_elastic_beanstalk_environment": ("compute.paas", "beanstalk"),
    # billed by the hour (ticket 2026-10-21-infra-bundled-prices-missing-common-aws-rows): no longer parts
    "aws_nat_gateway": ("gateway.nat", "vpc.nat"), "aws_eip": ("network.ip", "vpc.ipv4"),
    "aws_lb": ("load_balancer", "elb"), "aws_alb": ("load_balancer", "elb"), "aws_elb": ("load_balancer", "elb.classic"),
    "aws_cloudfront_distribution": ("edge.cdn", "cloudfront"), "aws_route53_zone": ("edge.dns", "route53"),
    "aws_wafv2_web_acl": ("edge.waf", "waf"), "aws_waf_web_acl": ("edge.waf", "waf"),
    "aws_api_gateway_rest_api": ("gateway.api", "apigateway"), "aws_apigatewayv2_api": ("gateway.api", "apigateway"),
    "aws_db_instance": ("database.relational", "rds"), "aws_rds_cluster": ("database.relational", "aurora"),
    "aws_dynamodb_table": ("database.kv", "dynamodb"), "aws_docdb_cluster": ("database.document", "docdb"),
    "aws_elasticache_cluster": ("cache", "elasticache"), "aws_elasticache_replication_group": ("cache", "elasticache"),
    "aws_elasticache_serverless_cache": ("cache", "elasticache"),
    "aws_opensearch_domain": ("database.search", "opensearch"), "aws_elasticsearch_domain": ("database.search", "opensearch"),
    "aws_s3_bucket": ("storage.object", "s3"), "aws_efs_file_system": ("storage.file", "efs"),
    "aws_ebs_volume": ("storage.block", "ebs"), "aws_sqs_queue": ("queue", "sqs"), "aws_sns_topic": ("queue", "sns"),
    "aws_cloudwatch_event_rule": ("scheduler", "eventbridge"), "aws_scheduler_schedule": ("scheduler", "scheduler"),
    "aws_kinesis_stream": ("stream", "kinesis"), "aws_msk_cluster": ("stream", "msk"),
    "aws_sfn_state_machine": ("compute.function", "stepfunctions"),
    "aws_ses_domain_identity": ("mail", "ses"), "aws_sesv2_email_identity": ("mail", "ses"),
    "aws_cognito_user_pool": ("auth", "cognito"), "aws_secretsmanager_secret": ("secrets", "secretsmanager"),
    "aws_kms_key": ("secrets", "kms"), "aws_ssm_parameter": ("secrets", "ssm"),
    "aws_cloudwatch_log_group": ("monitoring", "cloudwatch.logs"),
    "aws_cloudwatch_metric_alarm": ("monitoring.alarm", "cloudwatch"),
    "aws_iam_role": ("security.iam", "iam"), "aws_iam_user": ("security.iam", "iam"),
    "aws_iam_policy": ("security.policy", "iam"), "aws_ecr_repository": ("ci", "ecr"),
    "aws_codebuild_project": ("ci", "codebuild"), "aws_codepipeline": ("ci", "codepipeline"),
    "aws_vpc": ("group:network", "vpc"), "aws_subnet": ("group:subnet", "vpc"),
    # Google Cloud
    "google_compute_instance": ("compute.vm", "gce"),
    "google_compute_instance_group_manager": ("compute.vm", "gce.mig"),
    "google_compute_region_instance_group_manager": ("compute.vm", "gce.mig"),
    "google_cloud_run_service": ("compute.container", "run"), "google_cloud_run_v2_service": ("compute.container", "run"),
    "google_cloud_run_v2_job": ("compute.container", "run.job"),
    "google_cloudfunctions_function": ("compute.function", "functions"),
    "google_cloudfunctions2_function": ("compute.function", "functions"),
    "google_container_cluster": ("compute.k8s", "gke"), "google_app_engine_application": ("compute.paas", "appengine"),
    "google_sql_database_instance": ("database.relational", "cloudsql"),
    "google_spanner_instance": ("database.relational", "spanner"),
    "google_firestore_database": ("database.document", "firestore"), "google_bigtable_instance": ("database.kv", "bigtable"),
    "google_bigquery_dataset": ("database.relational", "bigquery"), "google_redis_instance": ("cache", "memorystore"),
    "google_storage_bucket": ("storage.object", "gcs"), "google_filestore_instance": ("storage.file", "filestore"),
    "google_compute_disk": ("storage.block", "pd"), "google_pubsub_topic": ("queue", "pubsub"),
    "google_cloud_tasks_queue": ("queue", "cloudtasks"), "google_cloud_scheduler_job": ("scheduler", "scheduler"),
    "google_compute_url_map": ("load_balancer", "lb"), "google_compute_security_policy": ("edge.waf", "armor"),
    "google_dns_managed_zone": ("edge.dns", "clouddns"), "google_secret_manager_secret": ("secrets", "secretmanager"),
    "google_kms_crypto_key": ("secrets", "kms"), "google_api_gateway_api": ("gateway.api", "apigateway"),
    "google_identity_platform_config": ("auth", "identityplatform"),
    "google_monitoring_alert_policy": ("monitoring.alarm", "monitoring"),
    "google_service_account": ("security.iam", "iam"), "google_artifact_registry_repository": ("ci", "artifactregistry"),
    "google_compute_network": ("group:network", "vpc"), "google_compute_subnetwork": ("group:subnet", "vpc"),
    "google_project": ("group:project", "project"),
    # Azure
    "azurerm_linux_virtual_machine": ("compute.vm", "vm"), "azurerm_windows_virtual_machine": ("compute.vm", "vm"),
    "azurerm_virtual_machine": ("compute.vm", "vm"), "azurerm_linux_virtual_machine_scale_set": ("compute.vm", "vmss"),
    "azurerm_windows_virtual_machine_scale_set": ("compute.vm", "vmss"),
    "azurerm_container_app": ("compute.container", "containerapps"), "azurerm_container_group": ("compute.container", "aci"),
    "azurerm_kubernetes_cluster": ("compute.k8s", "aks"),
    "azurerm_linux_function_app": ("compute.function", "functions"),
    "azurerm_windows_function_app": ("compute.function", "functions"), "azurerm_function_app": ("compute.function", "functions"),
    "azurerm_linux_web_app": ("compute.paas", "appservice"), "azurerm_windows_web_app": ("compute.paas", "appservice"),
    "azurerm_app_service": ("compute.paas", "appservice"), "azurerm_static_web_app": ("compute.paas", "staticwebapps"),
    "azurerm_lb": ("load_balancer", "lb"), "azurerm_application_gateway": ("load_balancer", "appgateway"),
    "azurerm_cdn_frontdoor_profile": ("edge.cdn", "frontdoor"), "azurerm_frontdoor": ("edge.cdn", "frontdoor"),
    "azurerm_cdn_profile": ("edge.cdn", "cdn"), "azurerm_dns_zone": ("edge.dns", "dns"),
    "azurerm_web_application_firewall_policy": ("edge.waf", "waf"), "azurerm_api_management": ("gateway.api", "apim"),
    "azurerm_mssql_server": ("database.relational", "sql"),
    "azurerm_postgresql_flexible_server": ("database.relational", "postgresql"),
    "azurerm_mysql_flexible_server": ("database.relational", "mysql"),
    "azurerm_cosmosdb_account": ("database.document", "cosmosdb"), "azurerm_redis_cache": ("cache", "redis"),
    "azurerm_search_service": ("database.search", "search"), "azurerm_storage_account": ("storage.object", "storage"),
    "azurerm_storage_share": ("storage.file", "files"), "azurerm_managed_disk": ("storage.block", "disk"),
    "azurerm_servicebus_namespace": ("queue", "servicebus"), "azurerm_eventhub_namespace": ("stream", "eventhubs"),
    "azurerm_eventgrid_topic": ("queue", "eventgrid"), "azurerm_key_vault": ("secrets", "keyvault"),
    "azurerm_log_analytics_workspace": ("monitoring", "loganalytics"),
    "azurerm_application_insights": ("monitoring", "appinsights"),
    "azurerm_monitor_metric_alert": ("monitoring.alarm", "monitor"),
    "azurerm_user_assigned_identity": ("security.iam", "identity"), "azurerm_container_registry": ("ci", "acr"),
    "azurerm_virtual_network": ("group:network", "vnet"), "azurerm_subnet": ("group:subnet", "vnet"),
    # Cloudflare
    "cloudflare_zone": ("edge.dns", "zone"), "cloudflare_worker_script": ("compute.function", "workers"),
    "cloudflare_workers_script": ("compute.function", "workers"), "cloudflare_pages_project": ("compute.paas", "pages"),
    "cloudflare_workers_kv_namespace": ("database.kv", "kv"), "cloudflare_r2_bucket": ("storage.object", "r2"),
    "cloudflare_d1_database": ("database.relational", "d1"), "cloudflare_queue": ("queue", "queues"),
    "cloudflare_load_balancer": ("load_balancer", "lb"), "cloudflare_access_application": ("auth", "access"),
    "cloudflare_zero_trust_access_application": ("auth", "access"),
    # PaaS and the rest
    "vercel_project": ("compute.paas", "project"),
    "digitalocean_droplet": ("compute.vm", "droplet"), "digitalocean_app": ("compute.paas", "app"),
    "digitalocean_database_cluster": ("database.relational", "database"),
    "digitalocean_spaces_bucket": ("storage.object", "spaces"), "digitalocean_kubernetes_cluster": ("compute.k8s", "doks"),
    "digitalocean_loadbalancer": ("load_balancer", "lb"), "digitalocean_vpc": ("group:network", "vpc"),
    "heroku_app": ("compute.paas", "app"), "heroku_addon": ("external.saas", "addon"),
    "aws_lightsail_instance": ("compute.vm", "lightsail"), "aws_lightsail_database": ("database.relational", "lightsail"), "netlify_site": ("compute.paas", "site"),
    "kubernetes_deployment": ("compute.container", "deployment"),
    "kubernetes_deployment_v1": ("compute.container", "deployment"),
    "kubernetes_stateful_set": ("compute.container", "statefulset"),
    "kubernetes_stateful_set_v1": ("compute.container", "statefulset"),
    "kubernetes_ingress": ("load_balancer", "ingress"), "kubernetes_ingress_v1": ("load_balancer", "ingress"),
    "kubernetes_cron_job": ("scheduler", "cronjob"), "kubernetes_cron_job_v1": ("scheduler", "cronjob"),
    "kubernetes_namespace": ("group:namespace", "namespace"), "kubernetes_namespace_v1": ("group:namespace", "namespace"),
    "helm_release": ("compute.container", "helm"),
}
# A resource whose type ends so is part of another (a policy, an attachment, a rule, a record): counted, not drawn.
PART_SUFFIX = re.compile(
    r"_(?:policy|policies|attachment|attachments|association|rule|rules|listener|listener_rule|target_group|"
    r"target_group_attachment|route|route_table|routes|version|versioning|configuration|config|permission|"
    r"record|dns_record|member|binding|notification|lifecycle_configuration|encryption|"
    r"server_side_encryption_configuration|public_access_block|ownership_controls|acl|cors_configuration|website_configuration|"
    r"logging|mapping|integration|stage|deployment|resource|method|method_response|integration_response|"
    r"event_source_mapping|subscription|target|task_definition|node_group|launch_template|launch_configuration|"
    r"security_group|security_group_rule|internet_gateway|nat_gateway|eip|vpc_endpoint|key_pair|"
    r"parameter_group|subnet_group|option_group|domain|domain_name|custom_domain|certificate|"
    r"certificate_validation|alias|secret_version|log_stream|metric_filter|dashboard|cluster_instance|"
    r"database|user|service|secret|config_map|service_account|role|role_assignment|resource_group|service_plan|"
    r"storage_container|servicebus_queue|servicebus_topic|tag|tags|project_domain|project_environment_variable|"
    r"ruleset|worker_route|workers_route|workers_domain|addon|firewall|firewall_rule|peering|"
    r"network_interface|public_ip|network_security_group|image|disk_attachment|forwarding_rule|"
    r"global_forwarding_rule|backend_service|backend_bucket|health_check|http_proxy|https_proxy|"
    r"target_http_proxy|target_https_proxy|ssl_certificate|managed_ssl_certificate|neg|"
    r"region_network_endpoint_group|global_address|address|router|router_nat|iam_member|iam_binding|iam_policy)(?:_v\d+)?$")
PART_EXACT = {"aws_iam_role_policy", "aws_iam_role_policy_attachment", "aws_iam_policy_attachment",
              "aws_iam_instance_profile", "aws_ecs_capacity_provider", "aws_ecr_lifecycle_policy",
              "google_project_service", "google_project_iam_member", "azurerm_resource_group"}

# The service a price row is found by (ticket 2026-10-21-infra-bundled-prices-missing-common-aws-rows): the tables
# above say "rds" and "elb", the price rows "rds.mysql", "elb.alb" (the price book falls back from "rds.mysql" to "rds",
# never the other way), so a seeded RDS or load balancer had no price. Refined from what the resource says: its engine,
# its load balancer type (none written: AWS's default, application). What cannot be read (a variable) is not guessed.
RDS_ENGINE_SERVICE = {"mysql": "rds.mysql", "postgres": "rds.postgres", "mariadb": "rds.mariadb",
                      "aurora": "aurora.mysql", "aurora-mysql": "aurora.mysql", "aurora-postgresql": "aurora.postgres"}
LB_TYPE_SERVICE = {"application": "elb.alb", "network": "elb.nlb", "gateway": "elb.gwlb"}
LB_DEFAULT_TYPE = "application"


def priced_service(svc: str, engine: str | None = None, lb_type: str | None = None, lb_type_written: bool = False) -> str:
    """``svc`` as the price rows name it: rds -> rds.<engine> (aurora.<engine> for an Aurora engine), aurora ->
    aurora.mysql / aurora.postgres, elb -> elb.alb / elb.nlb. ``engine`` / ``lb_type``: the literal the resource gives,
    or None; ``lb_type_written``: the attribute is there (a variable when lb_type is None)."""
    if svc in ("rds", "aurora") and engine:
        return RDS_ENGINE_SERVICE.get(engine.strip().lower(), svc)
    if svc == "elb":
        if lb_type:
            return LB_TYPE_SERVICE.get(lb_type.strip().lower(), svc)
        if not lb_type_written:
            return LB_TYPE_SERVICE[LB_DEFAULT_TYPE]
    return svc


CFN_TYPES: dict[str, tuple[str, str]] = {
    "AWS::EC2::Instance": ("compute.vm", "ec2"), "AWS::AutoScaling::AutoScalingGroup": ("compute.vm", "ec2.asg"),
    "AWS::ECS::Service": ("compute.container", "ecs"), "AWS::ECS::Cluster": ("group:cluster", "ecs"),
    "AWS::EKS::Cluster": ("compute.k8s", "eks"), "AWS::Lambda::Function": ("compute.function", "lambda"),
    "AWS::Serverless::Function": ("compute.function", "lambda"),
    "AWS::Serverless::Api": ("gateway.api", "apigateway"), "AWS::Serverless::HttpApi": ("gateway.api", "apigateway"),
    "AWS::ApiGateway::RestApi": ("gateway.api", "apigateway"), "AWS::ApiGatewayV2::Api": ("gateway.api", "apigateway"),
    "AWS::AppRunner::Service": ("compute.paas", "apprunner"),
    "AWS::ElasticLoadBalancingV2::LoadBalancer": ("load_balancer", "elb"),
    "AWS::CloudFront::Distribution": ("edge.cdn", "cloudfront"), "AWS::Route53::HostedZone": ("edge.dns", "route53"),
    "AWS::WAFv2::WebACL": ("edge.waf", "waf"), "AWS::RDS::DBInstance": ("database.relational", "rds"),
    "AWS::RDS::DBCluster": ("database.relational", "aurora"), "AWS::DynamoDB::Table": ("database.kv", "dynamodb"),
    "AWS::Serverless::SimpleTable": ("database.kv", "dynamodb"),
    "AWS::ElastiCache::CacheCluster": ("cache", "elasticache"), "AWS::ElastiCache::ReplicationGroup": ("cache", "elasticache"),
    "AWS::OpenSearchService::Domain": ("database.search", "opensearch"), "AWS::S3::Bucket": ("storage.object", "s3"),
    "AWS::EFS::FileSystem": ("storage.file", "efs"), "AWS::SQS::Queue": ("queue", "sqs"), "AWS::SNS::Topic": ("queue", "sns"),
    "AWS::Events::Rule": ("scheduler", "eventbridge"), "AWS::Scheduler::Schedule": ("scheduler", "scheduler"),
    "AWS::EC2::NatGateway": ("gateway.nat", "vpc.nat"), "AWS::EC2::EIP": ("network.ip", "vpc.ipv4"),
    "AWS::Kinesis::Stream": ("stream", "kinesis"),
    "AWS::StepFunctions::StateMachine": ("compute.function", "stepfunctions"),
    "AWS::Serverless::StateMachine": ("compute.function", "stepfunctions"),
    "AWS::Cognito::UserPool": ("auth", "cognito"), "AWS::SecretsManager::Secret": ("secrets", "secretsmanager"),
    "AWS::KMS::Key": ("secrets", "kms"), "AWS::Logs::LogGroup": ("monitoring", "cloudwatch.logs"),
    "AWS::CloudWatch::Alarm": ("monitoring.alarm", "cloudwatch"), "AWS::IAM::Role": ("security.iam", "iam"),
    "AWS::IAM::User": ("security.iam", "iam"), "AWS::IAM::Policy": ("security.policy", "iam"),
    "AWS::IAM::ManagedPolicy": ("security.policy", "iam"), "AWS::ECR::Repository": ("ci", "ecr"),
    "AWS::SES::EmailIdentity": ("mail", "ses"), "AWS::EC2::VPC": ("group:network", "vpc"),
    "AWS::EC2::Subnet": ("group:subnet", "vpc"),
}
CFN_PARTS = {"Policy", "Permission", "Version", "Alias", "Listener", "ListenerRule", "TargetGroup", "Route",
             "RouteTable", "SubnetRouteTableAssociation", "SecurityGroup", "SecurityGroupIngress", "SecurityGroupEgress",
             "InternetGateway", "VPCGatewayAttachment", "BucketPolicy", "QueuePolicy",
             "TopicPolicy", "Subscription", "EventSourceMapping", "Deployment", "Stage", "Method", "Resource",
             "Integration", "Route", "LayerVersion", "TaskDefinition", "LogStream", "SubnetGroup", "DBSubnetGroup",
             "DBParameterGroup", "InstanceProfile", "RecordSet", "RecordSetGroup", "Certificate", "LaunchTemplate",
             "Authorizer", "ApiMapping", "DomainName", "UserPoolClient", "UserPoolDomain", "SecretTargetAttachment",
             "Metadata", "MountTarget", "CapacityProvider", "ClusterCapacityProviderAssociations", "VPCEndpoint",
             "OriginAccessControl", "CloudFrontOriginAccessIdentity", "WebACLAssociation", "Url"}

BICEP_TYPES: dict[str, tuple[str, str]] = {
    "microsoft.web/sites": ("compute.paas", "appservice"), "microsoft.web/staticsites": ("compute.paas", "staticwebapps"),
    "microsoft.storage/storageaccounts": ("storage.object", "storage"),
    "microsoft.sql/servers": ("database.relational", "sql"),
    "microsoft.dbforpostgresql/flexibleservers": ("database.relational", "postgresql"),
    "microsoft.dbformysql/flexibleservers": ("database.relational", "mysql"),
    "microsoft.documentdb/databaseaccounts": ("database.document", "cosmosdb"), "microsoft.cache/redis": ("cache", "redis"),
    "microsoft.keyvault/vaults": ("secrets", "keyvault"),
    "microsoft.containerservice/managedclusters": ("compute.k8s", "aks"),
    "microsoft.app/containerapps": ("compute.container", "containerapps"),
    "microsoft.compute/virtualmachines": ("compute.vm", "vm"), "microsoft.servicebus/namespaces": ("queue", "servicebus"),
    "microsoft.eventhub/namespaces": ("stream", "eventhubs"), "microsoft.insights/components": ("monitoring", "appinsights"),
    "microsoft.operationalinsights/workspaces": ("monitoring", "loganalytics"),
    "microsoft.managedidentity/userassignedidentities": ("security.iam", "identity"),
    "microsoft.cdn/profiles": ("edge.cdn", "frontdoor"), "microsoft.network/frontdoors": ("edge.cdn", "frontdoor"),
    "microsoft.apimanagement/service": ("gateway.api", "apim"),
    "microsoft.network/applicationgateways": ("load_balancer", "appgateway"),
    "microsoft.network/loadbalancers": ("load_balancer", "lb"),
    "microsoft.containerregistry/registries": ("ci", "acr"),
    "microsoft.network/virtualnetworks": ("group:network", "vnet"),
}
BICEP_PARTS = {"microsoft.web/serverfarms", "microsoft.authorization/roleassignments", "microsoft.network/publicipaddresses",
               "microsoft.network/networksecuritygroups", "microsoft.network/networkinterfaces",
               "microsoft.network/privateendpoints", "microsoft.network/privatednszones", "microsoft.resources/resourcegroups"}

# ---------------------------------------------------------------- Kubernetes manifests
K8S_WORKLOAD = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "Pod"}
K8S_PARTS = {"ConfigMap", "Secret", "ServiceAccount", "Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding",
             "NetworkPolicy", "HorizontalPodAutoscaler", "PodDisruptionBudget", "Kustomization", "PersistentVolume",
             "StorageClass", "LimitRange", "ResourceQuota", "Certificate", "Issuer", "ClusterIssuer", "ServiceMonitor",
             "PodMonitor", "PriorityClass", "VerticalPodAutoscaler", "Endpoints", "EndpointSlice", "Namespace"}


def k8s_mapping(kind: str, spec: dict | None = None):
    """(category, service) of a manifest's kind; "part" for what is part of another; None when it has no mapping. A
    workload is a container (compute.k8s is the cluster: EKS, GKE, AKS); a Service is a node only as a load balancer
    (LoadBalancer, NodePort), a ClusterIP one is a part."""
    if kind in K8S_WORKLOAD:
        return "compute.container", f"k8s.{kind.lower()}"
    if kind == "CronJob":
        return "scheduler", "k8s.cronjob"
    if kind in ("Ingress", "Gateway", "HTTPRoute"):
        return "load_balancer", f"k8s.{kind.lower()}"
    if kind == "PersistentVolumeClaim":
        return "storage.block", "k8s.pvc"
    if kind == "Service":
        return ("load_balancer", "k8s.service") if (spec or {}).get("type") in ("LoadBalancer", "NodePort") else "part"
    if kind in K8S_PARTS:
        return "part"
    return None


# ---------------------------------------------------------------- Docker Compose (an image's name tells the kind)
COMPOSE_IMAGE = (("postgres", "database.relational"), ("mysql", "database.relational"), ("mariadb", "database.relational"),
                 ("mongo", "database.document"), ("redis", "cache"), ("valkey", "cache"), ("memcached", "cache"),
                 ("rabbitmq", "queue"), ("kafka", "stream"), ("elasticsearch", "database.search"),
                 ("opensearch", "database.search"), ("minio", "storage.object"), ("nginx", "load_balancer"),
                 ("traefik", "load_balancer"), ("mailhog", "mail"), ("mailpit", "mail"))


def compose_category(image: str | None) -> str:
    low = (image or "").lower()
    return next((c for key, c in COMPOSE_IMAGE if key in low), "compute.container")


# ---------------------------------------------------------------- Cloudflare wrangler bindings
# (address kind, where the list is, category, service, the keys that name the binding)
WRANGLER_BINDINGS = (("kv_namespaces", ("kv_namespaces",), "database.kv", "kv", ("binding",)),
                     ("r2_buckets", ("r2_buckets",), "storage.object", "r2", ("binding", "bucket_name")),
                     ("d1_databases", ("d1_databases",), "database.relational", "d1", ("binding", "database_name")),
                     ("durable_objects", ("durable_objects", "bindings"), "database.kv", "durable-objects", ("name", "class_name")),
                     ("queues.producers", ("queues", "producers"), "queue", "queues", ("binding", "queue")),
                     ("queues.consumers", ("queues", "consumers"), "queue", "queues", ("queue",)))


def wrangler_bindings(cfg: dict):
    """(address kind, handle, label, category, service) of every binding a wrangler config declares."""
    for kind, path, cat, svc, keys in WRANGLER_BINDINGS:
        items = cfg
        for p in path:
            items = items.get(p) if isinstance(items, dict) else None
        for b in items or []:
            if not isinstance(b, dict):
                continue
            handle = next((str(b[k]) for k in keys if b.get(k)), None)
            if handle:
                yield kind, handle, handle, cat, svc


# ---------------------------------------------------------------- mappings
CFN_SKIP_PREFIX = ("Custom::", "AWS::CDK::", "AWS::CloudFormation::")


def tf_provider(type_: str) -> str | None:
    """The provider of a Terraform resource type by its prefix; None for a utility provider (random, null, ...)."""
    prefix = type_.split("_", 1)[0]
    if prefix in TF_UTILITY:
        return None
    return TF_PROVIDER.get(prefix, prefix)


def tf_mapping(type_: str):
    """(category, service), "part", or None (no mapping)."""
    if type_ in TF_TYPES:
        return TF_TYPES[type_]
    if type_ in PART_EXACT or PART_SUFFIX.search(type_):
        return "part"
    return None


def cfn_mapping(type_: str):
    if type_ in CFN_TYPES:
        return CFN_TYPES[type_]
    if type_.startswith(CFN_SKIP_PREFIX) or type_.rsplit("::", 1)[-1] in CFN_PARTS:
        return "part"
    return None


def bicep_mapping(type_: str):
    low = type_.lower()
    if low in BICEP_TYPES:
        return BICEP_TYPES[low]
    if low in BICEP_PARTS or low.count("/") > 1:
        return "part"
    return None


def optional(category: str) -> bool:
    """Folded by default (IAM, policy, alarm): check compares it when declared and is silent when it is not."""
    return category in M.FOLDED_BY_DEFAULT


# ---------------------------------------------------------------- reading HCL (seed and check alike)
TF_RESOURCE = re.compile(r'^[ \t]*resource\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"\s*\{', re.M)
HEREDOC = re.compile(r"<<-?\s*([A-Za-z_][A-Za-z0-9_]*)[^\n]*\n")


def block_end(text: str, i: int) -> int:
    """The index of the brace that closes the one at i (strings, comments and heredocs skipped); len(text) if none."""
    depth, n, j = 0, len(text), i
    while j < n:
        c = text[j]
        if c == '"':
            j += 1
            while j < n and text[j] != '"' and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
        elif c == "#" or text.startswith("//", j):
            k = text.find("\n", j)
            j = n if k < 0 else k
            continue
        elif text.startswith("/*", j):
            k = text.find("*/", j + 2)
            j = n if k < 0 else k + 2
            continue
        elif text.startswith("<<", j):
            m = HEREDOC.match(text, j)
            if m:
                end = re.compile(r"^\s*" + re.escape(m.group(1)) + r"\s*$", re.M).search(text, m.end())
                j = n if end is None else end.end()
                continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return n


# ---------------------------------------------------------------- a node's spec (the server room ticket's §4)
# The attributes of a resource that are its spec, IaC name -> the model's spec key, in the order the display lists them.
# seed drafts a node's spec from them, check compares a declared spec with them; only a value written as it is (a
# string, a number, true or false) is read: a variable, a reference, a function or "${...}" is not evaluated.
TF_SPEC = (("instance_type", "instance_type"), ("instance_class", "instance_class"), ("node_type", "node_type"),
           ("machine_type", "machine_type"), ("tier", "tier"), ("engine_version", "version"),
           ("allocated_storage", "storage_gb"), ("storage_type", "storage_type"), ("memory_size", "memory_mb"),
           ("timeout", "timeout_s"), ("runtime", "runtime"), ("multi_az", "multi_az"), ("num_cache_nodes", "nodes"),
           ("desired_count", "tasks"), ("cpu", "cpu"), ("memory", "memory"))
CFN_SPEC = (("InstanceType", "instance_type"), ("DBInstanceClass", "instance_class"), ("CacheNodeType", "node_type"),
            ("EngineVersion", "version"), ("AllocatedStorage", "storage_gb"), ("StorageType", "storage_type"),
            ("MemorySize", "memory_mb"), ("Timeout", "timeout_s"), ("Runtime", "runtime"), ("MultiAZ", "multi_az"),
            ("NumCacheNodes", "nodes"), ("DesiredCount", "tasks"))
SPEC_KEYS = tuple(dict.fromkeys(k for _a, k in TF_SPEC + CFN_SPEC))   # every key the tables give


def _spec_scalar(v) -> str | None:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str) and v.strip() and "${" not in v and len(v) <= 120:
        return v
    return None


def _spec_find(value, attr: str):
    """The first value written as it is under the key attr anywhere in a parsed body (a block nests: settings.tier)."""
    if isinstance(value, dict):
        if attr in value and _spec_scalar(value[attr]) is not None:
            return _spec_scalar(value[attr])
        for v in value.values():
            got = _spec_find(v, attr)
            if got is not None:
                return got
    elif isinstance(value, list):
        for v in value:
            got = _spec_find(v, attr)
            if got is not None:
                return got
    return None


def tf_spec(body) -> list[dict]:
    """A Terraform resource's spec: body is the HCL text between its braces, or the parsed JSON of a .tf.json one."""
    out = []
    for attr, key in TF_SPEC:
        if isinstance(body, str):
            m = re.search(r'^\s*' + attr + r'\s*=\s*(?:"([^"$]*)"|(-?\d+(?:\.\d+)?|true|false))\s*(?:[#/].*)?$', body, re.M)
            got = (m.group(1) if m.group(1) is not None else m.group(2)) if m else None
            got = got if got is not None and got.strip() and len(got) <= 120 else None
        else:
            got = _spec_find(body, attr)
        if got is not None:
            out.append({"key": key, "value": got})
    return out


def cfn_spec(properties) -> list[dict]:
    """A CloudFormation resource's spec from its Properties (a !Ref, !GetAtt or !Sub is not a value written)."""
    out = []
    if isinstance(properties, dict):
        for attr, key in CFN_SPEC:
            got = _spec_scalar(properties.get(attr))
            if got is not None:
                out.append({"key": key, "value": got})
    return out


# ---------------------------------------------------------------- what sets a flow going (the server room ticket's item 7)
# Terraform resources that say what starts what, read by seed for the flows it drafts: type -> (the attribute naming
# the start, None for the resource itself; the attributes naming the target, any of them; the attribute holding the
# schedule as written, if any; the trigger; the action). Only references (<type>.<name>.<attr>) are followed: a
# variable, a string or a function is not.
TF_FLOW_SOURCES: dict[str, tuple[str | None, tuple[str, ...], str | None, str, str]] = {
    "aws_cloudwatch_event_target": ("rule", ("arn",), None, "event", "invoke"),
    "aws_scheduler_schedule": (None, ("arn",), "schedule_expression", "schedule", "invoke"),
    "google_cloud_scheduler_job": (None, ("uri", "topic_name"), "schedule", "schedule", "request"),
    "aws_lambda_event_source_mapping": ("event_source_arn", ("function_name",), None, "event", "dequeue"),
    "aws_s3_bucket_notification": ("bucket", ("lambda_function_arn", "queue_arn", "topic_arn"), None, "event", "invoke"),
}
#: an EventBridge rule with a schedule written in it makes its targets' flow a schedule's (a pattern: an event's)
TF_FLOW_RULE_SCHEDULE = {"aws_cloudwatch_event_rule": "schedule_expression"}


def tf_refs_of(body: str, attr: str) -> list[tuple[str, str]]:
    """(type, name) of each resource the attribute refers to in an HCL body (nested blocks too, a list of them too)."""
    if isinstance(body, dict):              # a .tf.json body: "${type.name.attr}" in the attribute's value, anywhere in it
        found = []

        def walk(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if k == attr:
                        found.append(json.dumps(x))
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(body)
        return [(t, n) for text in found for t, n in re.findall(r"(?<![\w.])([a-z][a-z0-9]*_[a-z0-9_]+)\.([A-Za-z_][A-Za-z0-9_-]*)\.", text)]
    out = []
    for m in re.finditer(r"^\s*" + attr + r"\s*=\s*(.*)$", body, re.M):
        out += [(t, n) for t, n in re.findall(r"(?<![\w.])([a-z][a-z0-9]*_[a-z0-9_]+)\.([A-Za-z_][A-Za-z0-9_-]*)\.", m.group(1))]
    return out


# ---------------------------------------------------------------- the iac addresses (boundary §3)
def tf_address(type_: str, name: str) -> str:
    return f"{type_}.{name}"            # a declared one may carry the module path: module.<m>.<type>.<name>


def cfn_address(logical_id: str) -> str:
    return logical_id                   # CloudFormation, SAM and cdk.out/*.template.json alike


def bicep_address(symbol: str) -> str:
    return symbol


def k8s_address(kind: str, name: str) -> str:
    return f"{kind}/{name}"


def compose_address(rel: str, service: str) -> str:
    return f"{rel}#services.{service}"  # rel: the compose file's path inside the room


# ---------------------------------------------------------------- which file is what (one copy: seed and check)
# The independent fourth verification R3 and (C)'s request: check and seed told IaC files apart each their own way (check read
# .tofu, k8s JSON, a CFN JSON not named template, "Resources:   # a note"; seed did not), so a draft from seed was
# warned about by check. What decides whether a file is IaC, of which kind and whose, lives here. (Which files hold
# values and are never opened — tfstate, .env, Pulumi stack and Helm values — is seed's own rule: check never opens
# them either, as it reads IaC and code by name only.)

#: folders neither reads (no symlink is followed, and hidden folders are left out too)
SKIP_DIRS = frozenset({".git", "node_modules", "vendor", "build", "dist", ".terraform", ".venv", "venv", "__pycache__",
                       "Pods", ".next", ".wrangler", "target", ".gradle", "DerivedData"})   # cdk.out is read: a synthesized CDK app
COMPOSE_NAMES = re.compile(r"^(?:docker-)?compose(?:\.[\w-]+)?\.ya?ml$")
WRANGLER_NAMES = re.compile(r"^wrangler\.(?:toml|json|jsonc)$")
_CFN_NAMED = re.compile(r"^(?:template|.+\.template|.+\.cfn)\.(?:json|ya?ml)$")
CFN_RESOURCES = re.compile(r'^[\'"]?Resources[\'"]?\s*:|"Resources"\s*:', re.M)   # YAML (quoted too) or JSON
CFN_TYPE = re.compile(r"\"?Type\"?\s*:\s*[\"']?AWS::")


def is_cfn(text: str) -> bool:
    """A CloudFormation / SAM template: its version line, or Resources with a Type of AWS:: (YAML or JSON, spaced or
    compact). A note that only mentions "AWS::" somewhere, or only one of the two, is not one."""
    return "AWSTemplateFormatVersion" in text or bool(CFN_RESOURCES.search(text) and CFN_TYPE.search(text))


def is_k8s(name: str, text: str) -> bool:
    """A Kubernetes manifest (or a List of them): apiVersion and kind at the line start in YAML, or as keys in JSON."""
    if re.search(r"^apiVersion:", text, re.M) and re.search(r"^kind:", text, re.M):
        return True
    return name.endswith(".json") and '"apiVersion"' in text and '"kind"' in text


def iac_kind(rel: str) -> str | None:
    """What an IaC file is by its name: terraform (.tf, .tofu), terraform_json (.tf.json), bicep, wrangler, compose,
    cfn (a template by name, a synthesized CDK template), by_text (another YAML or JSON: iac_kind_by_text decides), or
    None (not IaC)."""
    name = rel.rsplit("/", 1)[-1]
    if name.endswith(".tf.json"):
        return "terraform_json"
    if name.endswith((".tf", ".tofu")):
        return "terraform"
    if name.endswith(".bicep"):
        return "bicep"
    if WRANGLER_NAMES.match(name):
        return "wrangler"
    if COMPOSE_NAMES.match(name):
        return "compose"
    if ("/cdk.out/" in f"/{rel}" and name.endswith(".template.json")) or _CFN_NAMED.match(name):
        return "cfn"
    if name.endswith((".yaml", ".yml", ".json")):
        return "by_text"
    return None


def iac_kind_by_text(rel: str, text: str) -> str | None:
    """A YAML or JSON file of kind by_text: cfn, k8s, or None (not IaC)."""
    if is_cfn(text):
        return "cfn"
    if is_k8s(rel.rsplit("/", 1)[-1], text):
        return "k8s"
    return None


def iac_provider(rel: str) -> str:
    """Whose an IaC file is by its name ("*": anyone's — Terraform names many providers; a YAML or JSON by its text)."""
    kind = iac_kind(rel)
    return {"bicep": "azure", "cfn": "aws", "compose": "docker", "wrangler": "cloudflare"}.get(kind or "", "*")


def parse_jsonc(text: str):
    """wrangler.jsonc as `npm create cloudflare` writes it: JSON with // and /* */ comments and a "," after the last
    item. Strings are kept whole (a "//" or ",}" inside one is text); comments and a trailing "," are dropped; then
    json.loads. Raises ValueError when it is still not JSON (an unclosed string or comment included). One copy for
    seed (drafting) and check (comparing): The independent fourth verification R1 found check reading only whole-line "//"."""
    import json
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            if j >= n:
                raise ValueError("unclosed string")
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise ValueError("unclosed comment")
            i = j + 2
        elif c == ",":
            k = i + 1   # a "," whose next character, past spaces and comments, closes an object or a list is dropped
            while k < n:
                if text[k] in " \t\r\n":
                    k += 1
                elif text.startswith("//", k):
                    e = text.find("\n", k)
                    k = n if e < 0 else e
                elif text.startswith("/*", k):
                    e = text.find("*/", k + 2)
                    k = n if e < 0 else e + 2
                else:
                    break
            if k >= n or text[k] not in "}]":
                out.append(c)
            i += 1
        else:
            out.append(c)
            i += 1
    return json.loads("".join(out))


def wrangler_address(rel: str, kind: str | None = None, handle: str | None = None) -> str:
    return rel if kind is None else f"{rel}#{kind}.{handle}"


def paas_address(platform: str, name: str) -> str:
    return f"{platform}:{name}"         # firebase.json, render.yaml, serverless.yml, vercel / netlify / fly settings


# Platform settings files: file name -> (provider or None when the file does not say whose, the platform's address
# prefix). A Procfile runs on Heroku, Render, Dokku and others alike: its provider is not known from the file.
PAAS_FILES = {"firebase.json": ("firebase", "firebase"), "render.yaml": ("render", "render"),
              "serverless.yml": ("aws", "serverless"), "serverless.yaml": ("aws", "serverless"),
              "vercel.json": ("vercel", "vercel"), "netlify.toml": ("netlify", "netlify"), "fly.toml": ("fly", "fly"),
              "app.yaml": ("gcp", "appengine"), "Procfile": (None, "procfile")}
PAAS_PLATFORMS = {platform for _p, platform in PAAS_FILES.values()}


def paas_platform(address: str) -> str | None:
    """The platform of a platform-settings address (serverless:hello -> serverless), or None for any other form."""
    head = address.split(":", 1)[0] if ":" in address else ""
    return head if head in PAAS_PLATFORMS else None


def matches(declared: str, read: str) -> bool:
    """A declared address answers a read one: the same, or the declared one ends with it after a dot (module paths)."""
    return declared == read or declared.endswith("." + read)


_TF_ADDRESS = re.compile(r"(?:module\.[A-Za-z0-9_-]+(?:\[[^\]]*\])?\.)*(?:data\.)?[a-z][a-z0-9]*_[a-z0-9_]+\.[A-Za-z0-9_-]+(?:\[[^\]]*\])?")


def is_terraform_address(address: str) -> bool:
    """Whether an iac address has Terraform's form (<type>.<name>, with a module path or not): a Terraform file not
    read can only hide resources of this form."""
    return bool(_TF_ADDRESS.fullmatch(address))
