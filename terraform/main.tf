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

  name_prefix          = local.name_prefix
  environment          = var.environment
  ecr_repo_names       = var.ecr_repo_names
  tags                 = local.common_tags
  image_tag_mutability = "MUTABLE"
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

# 6. IAM Roles for per-queue API Producers, Workers, and KEDA via Pod Identity
module "iam" {
  source = "./modules/iam"

  name_prefix          = local.name_prefix
  cluster_name         = module.eks.cluster_name
  queue_arns           = module.sqs.queue_arns
  ecr_repo_arns        = module.ecr.repository_arns
  app_namespace        = local.namespaces.retailstore
  keda_namespace       = local.namespaces.keda
  enable_ecr_push_role = var.enable_ecr_push_role
  github_oidc_subjects = var.github_oidc_subjects
  tags                 = local.common_tags
}

# Karpenter AWS prerequisites. Keep index [0] for existing state addresses.
module "karpenter" {
  count               = 1
  source              = "./modules/karpenter"
  name_prefix         = local.name_prefix
  tags                = local.common_tags
  cluster_name        = module.eks.cluster_name
  karpenter_namespace = local.namespaces.karpenter
}
