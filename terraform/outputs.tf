# ── Networking ────────────────────────────────
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
  description = "Map of queue names to SQS queue URLs (consumed by Producer API and KEDA ScaledObject)"
  value       = module.sqs.queue_urls
}

output "sqs_queue_arns" {
  description = "Map of queue names to SQS queue ARNs (consumed by IAM module for IRSA policies)"
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
  description = "Security group ID shared by worker nodes (tagged for Karpenter discovery)"
  value       = module.eks.node_security_group_id
}

output "eks_oidc_provider_arn" {
  description = "ARN of the IAM OIDC Provider for the cluster"
  value       = module.eks.oidc_provider_arn
}

output "eks_oidc_issuer_url" {
  description = "The URL on the EKS cluster for the OpenID Connect identity provider"
  value       = module.eks.oidc_issuer_url
}

output "eks_node_role_arn" {
  description = "ARN of the IAM role used by worker nodes (for Karpenter EC2NodeClass)"
  value       = module.eks.node_role_arn
}

output "eks_node_role_name" {
  description = "Name of the IAM role used by worker nodes"
  value       = module.eks.node_role_name
}

