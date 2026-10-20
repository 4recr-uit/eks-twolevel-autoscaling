# ── Karpenter Controller IAM Outputs ───────────────────────────────────────────
output "controller_role_arn" {
  description = "ARN of the IAM Role used by the Karpenter controller"
  value       = aws_iam_role.controller.arn
}

output "controller_role_name" {
  description = "Name of the IAM Role used by the Karpenter controller"
  value       = aws_iam_role.controller.name
}

# ── Karpenter Node IAM Outputs ─────────────────────────────────────────────────
output "node_role_arn" {
  description = "ARN of the dedicated IAM role used by Karpenter-managed EC2 nodes"
  value       = aws_iam_role.node.arn
}

output "node_role_name" {
  description = "Name of the dedicated IAM role referenced by EC2NodeClass"
  value       = aws_iam_role.node.name
}

output "node_access_entry_arn" {
  description = "ARN of the EC2_LINUX EKS access entry for Karpenter-managed nodes"
  value       = aws_eks_access_entry.karpenter_node.access_entry_arn
}

# ── Interruption Queue Outputs ─────────────────────────────────────────────────
output "interruption_queue_arn" {
  description = "ARN of the SQS interruption queue used by Karpenter"
  value       = aws_sqs_queue.interruption.arn
}

output "interruption_queue_name" {
  description = "Name of the SQS interruption queue"
  value       = aws_sqs_queue.interruption.name
}

output "interruption_queue_url" {
  description = "URL of the SQS interruption queue"
  value       = aws_sqs_queue.interruption.url
}

# ── Karpenter Custom Resource Outputs ──────────────────────────────────────────
output "node_class_name" {
  description = "Name of the provisioned EC2NodeClass custom resource"
  value       = "default"
}

output "node_pool_name" {
  description = "Name of the provisioned NodePool custom resource"
  value       = "default"
}
