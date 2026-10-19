# 1. Networking (VPC, Subnets, IGW, NAT)
module "networking" {
  source = "./modules/networking"

  name_prefix          = local.name_prefix
  cluster_name         = local.cluster_name
  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
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
  tags                    = local.common_tags
}

# 5. IAM Roles for Application Pods (Producer, Worker, KEDA) via Pod Identity
module "iam" {
  source = "./modules/iam"

  name_prefix    = local.name_prefix
  cluster_name   = module.eks.cluster_name
  queue_arns     = module.sqs.queue_arns
  dlq_arns       = module.sqs.dlq_arns
  ecr_repo_arns  = module.ecr.repository_arns
  app_namespace  = local.namespaces.retailstore
  keda_namespace = local.namespaces.keda
  tags           = local.common_tags
}
