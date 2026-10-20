# ── Identifiers & Naming ──────────────────────
variable "name_prefix" {
  description = "Prefix applied to all created EKS resources"
  type        = string
  default     = "eks"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.32"

  validation {
    condition     = can(regex("^1\\.[0-9]+$", var.cluster_version))
    error_message = "cluster_version must be in standard Kubernetes format (e.g. '1.32')."
  }
}

# ── Network Configuration ─────────────────────
variable "vpc_id" {
  description = "ID of the VPC where the cluster and nodes reside"
  type        = string
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for control plane public endpoint cross-account ENIs"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for EKS worker nodes"
  type        = list(string)
}

# ── Seed Managed Node Group ───────────────────
variable "node_instance_types" {
  description = "EC2 instance types for the seed managed node group (system workloads)"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_group_capacity_type" {
  description = "Capacity type for seed node group: ON_DEMAND or SPOT"
  type        = string
  default     = "ON_DEMAND"

  validation {
    condition     = contains(["ON_DEMAND", "SPOT"], var.node_group_capacity_type)
    error_message = "node_group_capacity_type must be either 'ON_DEMAND' or 'SPOT'."
  }
}

variable "node_group_min_size" {
  description = "Minimum number of nodes in the seed managed node group"
  type        = number
  default     = 1
}

variable "node_group_max_size" {
  description = "Maximum number of nodes in the seed managed node group"
  type        = number
  default     = 3
}

variable "node_group_desired_size" {
  description = "Desired number of nodes in the seed managed node group"
  type        = number
  default     = 2
}

# ── Tagging ───────────────────────────────────
variable "tags" {
  description = "Common tags applied to all AWS resources"
  type        = map(string)
  default     = {}
}
