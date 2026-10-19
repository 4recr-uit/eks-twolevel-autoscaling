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
