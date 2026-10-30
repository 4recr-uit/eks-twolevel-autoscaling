# ── API Producer Outputs (publisher names retained for compatibility) ──────────────────────────────
output "publisher_role_arns" {
  description = "Pod Identity IAM role ARNs for API producers, keyed by main queue"
  value       = { for queue_name, role in aws_iam_role.publisher : queue_name => role.arn }
}

output "publisher_service_accounts" {
  description = "API producer ServiceAccount names, keyed by main queue"
  value       = local.publisher_service_accounts
}

# ── Worker Outputs ────────────────────────────────────────
output "worker_role_arns" {
  description = "Pod Identity IAM role ARNs for workers, keyed by main queue"
  value       = { for queue_name, role in aws_iam_role.worker : queue_name => role.arn }
}

output "worker_service_accounts" {
  description = "Worker ServiceAccount names, keyed by main queue"
  value       = local.worker_service_accounts
}

# ── KEDA Operator Outputs ─────────────────────────────────
output "keda_role_arn" {
  description = "ARN of the IAM Role for the KEDA operator (used in Pod Identity Association)"
  value       = aws_iam_role.keda.arn
}

output "keda_role_name" {
  description = "Name of the IAM Role for the KEDA operator"
  value       = aws_iam_role.keda.name
}

# ── ECR Push Outputs (conditional) ───────────────────────
output "ecr_push_role_arn" {
  description = "ARN of the IAM Role for CI/CD ECR image push. Empty string when enable_ecr_push_role = false."
  value       = var.enable_ecr_push_role ? aws_iam_role.ecr_push[0].arn : ""
}

output "ecr_push_role_name" {
  description = "Name of the IAM Role for CI/CD ECR image push. Empty string when enable_ecr_push_role = false."
  value       = var.enable_ecr_push_role ? aws_iam_role.ecr_push[0].name : ""
}
