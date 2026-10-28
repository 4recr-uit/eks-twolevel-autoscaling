# ── Cluster Outputs ───────────────────────────────────────────────────────────
output "cluster_id" {
  description = "ID of the EKS Cluster"
  value       = aws_eks_cluster.this.id
}

output "cluster_name" {
  description = "Name of the EKS Cluster"
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "Endpoint for EKS control plane API server (used by Helm/Kubernetes providers)"
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_version" {
  description = "Kubernetes version running on the cluster"
  value       = aws_eks_cluster.this.version
}

output "cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster"
  value       = aws_eks_cluster.this.certificate_authority[0].data
}

# ── Security Group Outputs ───────────────────────────────────────────────────
output "cluster_primary_security_group_id" {
  description = "Cluster security group created and managed automatically by EKS"
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "control_plane_security_group_id" {
  description = "Security group ID attached to the EKS control plane"
  value       = aws_security_group.cluster.id
}

output "node_security_group_id" {
  description = "Node security group attached to seed and Karpenter nodes; use as future RDS ingress source"
  value       = aws_security_group.node.id
}

# ── Node Group & IAM Outputs ─────────────────────────────────────────────────
output "node_role_arn" {
  description = "ARN of the IAM role used only by the seed EKS Managed Node Group"
  value       = aws_iam_role.node.arn
}

output "node_role_name" {
  description = "Name of the IAM role used only by the seed EKS Managed Node Group"
  value       = aws_iam_role.node.name
}

output "system_node_group_id" {
  description = "ID of the seed managed node group"
  value       = aws_eks_node_group.system.id
}

output "system_node_group_arn" {
  description = "ARN of the seed managed node group"
  value       = aws_eks_node_group.system.arn
}
