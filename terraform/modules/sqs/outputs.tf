# ── Main Queue Outputs ────────────────────────────────────────────────────────
output "queue_urls" {
  description = "Map of queue logical names to their SQS queue URLs (used by Producer and KEDA ScaledObject)"
  value       = { for k, v in aws_sqs_queue.this : k => v.url }
}

output "queue_arns" {
  description = "Map of queue logical names to their SQS queue ARNs (used by IAM module for IRSA policies)"
  value       = { for k, v in aws_sqs_queue.this : k => v.arn }
}

output "queue_names" {
  description = "Map of queue logical names to their actual SQS queue names on AWS"
  value       = { for k, v in aws_sqs_queue.this : k => v.name }
}

# ── Dead Letter Queue Outputs ─────────────────────────────────────────────────
output "dlq_urls" {
  description = "Map of queue logical names to their Dead Letter Queue URLs"
  value       = { for k, v in aws_sqs_queue.dlq : k => v.url }
}

output "dlq_arns" {
  description = "Map of queue logical names to their Dead Letter Queue ARNs"
  value       = { for k, v in aws_sqs_queue.dlq : k => v.arn }
}
