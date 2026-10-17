locals {
  # Standardized prefix for all resources
  name_prefix = "${var.project_name}-${var.environment}"

  # Common tags attached to all AWS resources
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Repository  = "eks-twolevel-autoscaling"
  }

  # Cluster name
  cluster_name = local.name_prefix

  # Centralized namespace definitions
  namespaces = {
    retailstore = "retailstore"
    monitoring  = var.monitoring_namespace
    keda        = var.keda_namespace
    karpenter   = var.karpenter_namespace
  }
}
