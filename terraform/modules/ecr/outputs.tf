output "repository_urls" {
  description = "Map of service names to their respective ECR repository URLs"
  value       = { for k, v in aws_ecr_repository.this : k => v.repository_url }
}

output "repository_arns" {
  description = "Map of service names to their respective ECR repository ARNs"
  value       = { for k, v in aws_ecr_repository.this : k => v.arn }
}

output "repository_names" {
  description = "Map of service names to their respective ECR repository names"
  value       = { for k, v in aws_ecr_repository.this : k => v.name }
}

output "registry_id" {
  description = "Registry ID where the ECR repositories reside"
  value       = length(aws_ecr_repository.this) > 0 ? values(aws_ecr_repository.this)[0].registry_id : null
}
