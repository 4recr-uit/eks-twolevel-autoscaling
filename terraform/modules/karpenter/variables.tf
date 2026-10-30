# ── Identifiers & Naming ────────────────────────────────────────────────────────
variable "name_prefix" {
  description = "Prefix applied to all AWS resources created by this module"
  type        = string
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

# ── Karpenter Pod Identity Configuration ──────────────────────────────────
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
