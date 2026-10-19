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
