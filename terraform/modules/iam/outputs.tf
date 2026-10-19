# ── Producer API Outputs ──────────────────────────────────
output "producer_role_arn" {
  description = "ARN of the IAM Role for the producer-api pod (used in Kubernetes ServiceAccount annotation or Pod Identity)"
  value       = aws_iam_role.producer.arn
}

output "producer_role_name" {
  description = "Name of the IAM Role for the producer-api pod"
  value       = aws_iam_role.producer.name
}

# ── Worker Outputs ────────────────────────────────────────
output "worker_role_arn" {
  description = "ARN of the IAM Role for the worker pod (used in Kubernetes ServiceAccount annotation or Pod Identity)"
  value       = aws_iam_role.worker.arn
}

output "worker_role_name" {
  description = "Name of the IAM Role for the worker pod"
  value       = aws_iam_role.worker.name
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
