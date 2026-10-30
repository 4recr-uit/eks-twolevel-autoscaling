output "platform_contract" {
  description = "Non-secret, versioned inputs for Bash deployment scripts."
  value = {
    schema_version            = 1
    account_id                = data.aws_caller_identity.current.account_id
    region                    = var.aws_region
    environment               = var.environment
    cluster_name              = module.eks.cluster_name
    cluster_endpoint          = module.eks.cluster_endpoint
    kubernetes_version        = var.cluster_version
    namespaces                = local.namespaces
    node_role                 = module.karpenter[0].node_role_name
    interruption_queue        = module.karpenter[0].interruption_queue_name
    security_group_ids        = [module.eks.cluster_primary_security_group_id, module.eks.node_security_group_id]
    queue_urls                = module.sqs.queue_urls
    ecr_urls                  = module.ecr.repository_urls
    postgres_host             = module.databases.postgres_endpoint
    mysql_host                = module.databases.mysql_endpoint
    api_accounts              = module.iam.publisher_service_accounts
    worker_accounts           = module.iam.worker_service_accounts
    keda_service_account      = "keda-operator"
    karpenter_service_account = "karpenter"
  }
}
