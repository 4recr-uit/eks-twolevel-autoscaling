# 1. Networking (VPC, public, EKS workload, and isolated RDS subnets)
module "networking" {
  source = "./modules/networking"

  name_prefix           = local.name_prefix
  cluster_name          = local.cluster_name
  vpc_cidr              = var.vpc_cidr
  availability_zones    = var.availability_zones
  public_subnet_cidrs   = var.public_subnet_cidrs
  private_subnet_cidrs  = var.private_subnet_cidrs
  database_subnet_cidrs = var.database_subnet_cidrs
}

# 2. ECR Repositories
module "ecr" {
  source = "./modules/ecr"

  name_prefix    = local.name_prefix
  environment    = var.environment
  ecr_repo_names = var.ecr_repo_names
  tags           = local.common_tags
}

# 3. SQS Queues (Worker task queues + Dead Letter Queues)
module "sqs" {
  source = "./modules/sqs"

  name_prefix            = local.name_prefix
  environment            = var.environment
  sqs_queue_names        = var.sqs_queue_names
  sqs_visibility_timeout = var.sqs_visibility_timeout
  sqs_message_retention  = var.sqs_message_retention
  tags                   = local.common_tags
}

# 4. EKS Cluster (Control Plane, Seed Managed Node Group, Pod Identity Agent)
module "eks" {
  source = "./modules/eks"

  name_prefix             = local.name_prefix
  cluster_name            = local.cluster_name
  cluster_version         = var.cluster_version
  vpc_id                  = module.networking.vpc_id
  public_subnet_ids       = module.networking.public_subnet_ids
  private_subnet_ids      = module.networking.private_subnet_ids
  node_instance_types     = var.node_instance_types
  node_group_min_size     = var.node_group_min_size
  node_group_max_size     = var.node_group_max_size
  node_group_desired_size = var.node_group_desired_size
  public_access_cidrs     = var.eks_public_access_cidrs
  tags                    = local.common_tags
}

# 5. Two private Single-AZ RDS instances (PostgreSQL and MySQL)
module "databases" {
  source = "./modules/databases"

  name_prefix             = local.name_prefix
  vpc_id                  = module.networking.vpc_id
  database_subnet_ids     = module.networking.database_subnet_ids
  node_security_group_id  = module.eks.node_security_group_id
  postgres_engine_version = var.postgres_engine_version
  mysql_engine_version    = var.mysql_engine_version
  db_instance_class       = var.db_instance_class
  allocated_storage       = var.db_allocated_storage
  backup_retention_days   = var.db_backup_retention_days
  deletion_protection     = var.db_deletion_protection
  create_final_snapshot   = var.db_create_final_snapshot
  tags                    = local.common_tags
}

# 6. IAM Roles for per-queue Outbox Publishers, Workers, and KEDA via Pod Identity
module "iam" {
  source = "./modules/iam"

  name_prefix    = local.name_prefix
  cluster_name   = module.eks.cluster_name
  queue_arns     = module.sqs.queue_arns
  ecr_repo_arns  = module.ecr.repository_arns
  app_namespace  = local.namespaces.retailstore
  keda_namespace = local.namespaces.keda
  tags           = local.common_tags
}

# 7. Karpenter Autoscaling (Interruption Queue, Controller IAM, Helm Releases & NodePool)
module "karpenter" {
  count  = var.enable_cluster_addons ? 1 : 0
  source = "./modules/karpenter"

  name_prefix                       = local.name_prefix
  environment                       = var.environment
  tags                              = local.common_tags
  cluster_name                      = module.eks.cluster_name
  cluster_endpoint                  = module.eks.cluster_endpoint
  cluster_primary_security_group_id = module.eks.cluster_primary_security_group_id
  node_security_group_id            = module.eks.node_security_group_id
  karpenter_version                 = var.karpenter_version
  karpenter_namespace               = local.namespaces.karpenter

  # Wait for the EKS Pod Identity agent and seed node group before Helm starts.
  depends_on = [module.eks]
}

# 8. KEDA Operator and SQS worker autoscaling
module "keda" {
  count  = var.enable_cluster_addons ? 1 : 0
  source = "./modules/keda"

  keda_version          = var.keda_version
  keda_namespace        = local.namespaces.keda
  app_namespace         = local.namespaces.retailstore
  aws_region            = var.aws_region
  queue_urls            = module.sqs.queue_urls
  enable_scaled_objects = var.enable_keda_scaled_objects
  queue_length          = var.keda_queue_length
  min_replica_count     = var.keda_min_replica_count
  max_replica_count     = var.keda_max_replica_count
  polling_interval      = var.keda_polling_interval
  cooldown_period       = var.keda_cooldown_period

  worker_deployments = {
    "cart-queue"     = "cart-worker"
    "checkout-queue" = "checkout-worker"
    "orders-queue"   = "orders-worker"
  }

  # The seed nodes, Pod Identity agent, and KEDA IAM association must exist first.
  depends_on = [module.eks, module.iam]
}

# 9. Optional local-only metrics UI for the experiment phase
module "observability" {
  count  = var.enable_observability ? 1 : 0
  source = "./modules/observability"

  namespace                 = var.monitoring_namespace
  chart_version             = var.monitoring_chart_version
  grafana_admin_secret_name = var.grafana_admin_secret_name

  depends_on = [module.eks]
}
