# ── Networking ────────────────────────────────
output "monthly_budget_name" {
  description = "Name of the AWS monthly cost budget"
  value       = aws_budgets_budget.monthly_cost.name
}

output "vpc_id" {
  description = "ID of the main VPC"
  value       = module.networking.vpc_id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = module.networking.vpc_cidr
}

output "public_subnet_ids" {
  description = "List of IDs of the public subnets"
  value       = module.networking.public_subnet_ids
}

output "private_subnet_ids" {
  description = "List of IDs of the private subnets"
  value       = module.networking.private_subnet_ids
}

output "public_subnet_cidrs" {
  description = "List of CIDR blocks of the public subnets"
  value       = module.networking.public_subnet_cidrs
}

output "private_subnet_cidrs" {
  description = "List of CIDR blocks of the private subnets"
  value       = module.networking.private_subnet_cidrs
}

output "database_subnet_ids" {
  description = "IDs of isolated RDS subnets in at least two availability zones"
  value       = module.networking.database_subnet_ids
}

output "database_subnet_cidrs" {
  description = "CIDR blocks of isolated RDS subnets"
  value       = module.networking.database_subnet_cidrs
}

output "database_route_table_id" {
  description = "Route table used by RDS subnets, without internet or NAT default route"
  value       = module.networking.database_route_table_id
}

output "postgres_endpoint" {
  description = "Private PostgreSQL hostname for retaildb (port 5432)"
  value       = module.databases.postgres_endpoint
}

output "mysql_endpoint" {
  description = "Private MySQL hostname for catalogdb (port 3306)"
  value       = module.databases.mysql_endpoint
}

output "postgres_master_secret_arn" {
  description = "RDS-managed bootstrap credential secret for PostgreSQL; do not use directly in app pods"
  value       = module.databases.postgres_master_secret_arn
}

output "mysql_master_secret_arn" {
  description = "RDS-managed bootstrap credential secret for MySQL; do not use directly in app pods"
  value       = module.databases.mysql_master_secret_arn
}

output "postgres_security_group_id" {
  description = "PostgreSQL SG: TCP 5432 from shared EKS node SG"
  value       = module.databases.postgres_security_group_id
}

output "mysql_security_group_id" {
  description = "MySQL SG: TCP 3306 from shared EKS node SG"
  value       = module.databases.mysql_security_group_id
}

output "nat_gateway_id" {
  description = "ID of the NAT Gateway"
  value       = module.networking.nat_gateway_id
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway"
  value       = module.networking.internet_gateway_id
}

output "vpc_endpoint_s3_id" {
  description = "ID of the S3 VPC Gateway Endpoint"
  value       = module.networking.vpc_endpoint_s3_id
}

# ── ECR ───────────────────────────────────────
output "ecr_repository_urls" {
  description = "Map of service names to ECR repository URLs"
  value       = module.ecr.repository_urls
}

output "ecr_repository_arns" {
  description = "Map of service names to ECR repository ARNs"
  value       = module.ecr.repository_arns
}

# ── SQS ───────────────────────────────────────
output "sqs_queue_urls" {
  description = "Map of queue names to SQS queue URLs (consumed by API producers, workers, and KEDA)"
  value       = module.sqs.queue_urls
}

output "sqs_queue_arns" {
  description = "Map of queue names to SQS queue ARNs (consumed by IAM policies for Pod Identity roles)"
  value       = module.sqs.queue_arns
}

output "sqs_dlq_urls" {
  description = "Map of queue names to Dead Letter Queue URLs"
  value       = module.sqs.dlq_urls
}

# ── EKS ───────────────────────────────────────
output "eks_cluster_id" {
  description = "ID of the EKS Cluster"
  value       = module.eks.cluster_id
}

output "eks_cluster_name" {
  description = "Name of the EKS Cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Endpoint for EKS control plane API server"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster"
  value       = module.eks.cluster_certificate_authority_data
}

output "eks_cluster_primary_security_group_id" {
  description = "Cluster security group managed automatically by EKS"
  value       = module.eks.cluster_primary_security_group_id
}

output "eks_node_security_group_id" {
  description = "Security group attached to seed and Karpenter nodes; use as future RDS ingress source"
  value       = module.eks.node_security_group_id
}

output "eks_node_role_arn" {
  description = "ARN of the IAM role used by the seed EKS Managed Node Group"
  value       = module.eks.node_role_arn
}

output "eks_node_role_name" {
  description = "Name of the IAM role used by the seed EKS Managed Node Group"
  value       = module.eks.node_role_name
}

# ── IAM ───────────────────────────────────────
output "iam_publisher_role_arns" {
  description = "Pod Identity IAM role ARNs for API producers, keyed by main queue"
  value       = module.iam.publisher_role_arns
}

output "iam_publisher_service_accounts" {
  description = "API producer ServiceAccount names, keyed by main queue"
  value       = module.iam.publisher_service_accounts
}

output "iam_worker_role_arns" {
  description = "Pod Identity IAM role ARNs for workers, keyed by main queue"
  value       = module.iam.worker_role_arns
}

output "iam_worker_service_accounts" {
  description = "Worker ServiceAccount names, keyed by main queue"
  value       = module.iam.worker_service_accounts
}

output "iam_keda_role_arn" {
  description = "ARN of the IAM Role for KEDA operator (Pod Identity)"
  value       = module.iam.keda_role_arn
}

output "iam_ecr_push_role_arn" {
  description = "ARN of the IAM Role for CI/CD ECR push (empty string if disabled)"
  value       = module.iam.ecr_push_role_arn
}

# ── Karpenter ─────────────────────────────────
output "karpenter_controller_role_arn" {
  description = "ARN of the IAM Role used by the Karpenter controller"
  value       = module.karpenter[0].controller_role_arn
}

output "karpenter_node_role_arn" {
  description = "ARN of the dedicated IAM role used by Karpenter-managed EC2 nodes"
  value       = module.karpenter[0].node_role_arn
}

output "karpenter_node_role_name" {
  description = "Name of the dedicated IAM role referenced by Karpenter EC2NodeClass"
  value       = module.karpenter[0].node_role_name
}

output "karpenter_node_access_entry_arn" {
  description = "ARN of the EC2_LINUX access entry for Karpenter-managed nodes"
  value       = module.karpenter[0].node_access_entry_arn
}

output "karpenter_interruption_queue_arn" {
  description = "ARN of the SQS interruption queue used by Karpenter"
  value       = module.karpenter[0].interruption_queue_arn
}

output "karpenter_interruption_queue_name" {
  description = "Name of the SQS interruption queue"
  value       = module.karpenter[0].interruption_queue_name
}
