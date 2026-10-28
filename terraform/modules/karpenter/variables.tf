# ── Identifiers & Naming ────────────────────────────────────────────────────────
variable "name_prefix" {
  description = "Prefix applied to all AWS resources created by this module"
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "tags" {
  description = "Resource tags applied to all AWS resources"
  type        = map(string)
  default     = {}
}

# ── EKS Cluster Configuration ──────────────────────────────────────────────────
variable "cluster_name" {
  description = "Name of the target EKS Cluster"
  type        = string
}

variable "cluster_endpoint" {
  description = "API server endpoint for the EKS Cluster"
  type        = string
}

variable "cluster_primary_security_group_id" {
  description = "EKS-managed primary cluster security group to attach to Karpenter nodes"
  type        = string
}

variable "node_security_group_id" {
  description = "Shared node security group to attach to Karpenter nodes and allow as future RDS ingress source"
  type        = string
}

# ── Karpenter Helm & Controller Configuration ──────────────────────────────────
variable "karpenter_version" {
  description = "Helm chart version for Karpenter"
  type        = string
  default     = "1.15.0"
}

variable "karpenter_namespace" {
  description = "Kubernetes namespace where Karpenter controller will be installed"
  type        = string
  default     = "karpenter"
}

variable "service_account_name" {
  description = "Name of the Kubernetes ServiceAccount used by Karpenter controller"
  type        = string
  default     = "karpenter"
}

# ── NodePool Provisioning Defaults ─────────────────────────────────────────────
variable "node_pool_cpu_limit" {
  description = "Total CPU limit provisionable across Karpenter-managed nodes"
  type        = string
  default     = "100"
}

variable "node_pool_memory_limit" {
  description = "Total memory limit provisionable across Karpenter-managed nodes"
  type        = string
  default     = "400Gi"
}

variable "node_pool_instance_categories" {
  description = "Allowed EC2 instance categories for worker nodes (e.g., c, m, t)"
  type        = list(string)
  default     = ["c", "m", "t"]
}

variable "node_pool_capacity_types" {
  description = "Allowed capacity types for Karpenter worker nodes (spot, on-demand)"
  type        = list(string)
  default     = ["on-demand"]
}

variable "consolidation_policy" {
  description = "Disruption consolidation policy for NodePool (WhenEmpty or WhenEmptyOrUnderutilized)"
  type        = string
  default     = "WhenEmptyOrUnderutilized"
}

variable "consolidate_after" {
  description = "Duration of underutilization/emptiness before node consolidation triggers"
  type        = string
  default     = "1m"
}
