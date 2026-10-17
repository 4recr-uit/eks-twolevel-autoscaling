# ── AWS ──────────────────────────────────────
variable "aws_region" {
  description = "AWS region for provisioning all resources"
  type        = string
  default     = "us-east-1"
}

# ── Project ───────────────────────────────────
variable "project_name" {
  description = "Project name used as prefix and tagging for all resources"
  type        = string
  default     = "twolevel-autoscaling"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

# ── Networking ────────────────────────────────
variable "vpc_cidr" {
  description = "CIDR block for the main VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of Availability Zones for subnet placement"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (for ALB and NAT Gateway)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (for EKS nodes)"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# ── EKS ──────────────────────────────────────
variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.32"
}

variable "node_instance_types" {
  description = "EC2 instance types for the seed managed node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_group_min_size" {
  description = "Minimum number of nodes in the managed node group"
  type        = number
  default     = 1
}

variable "node_group_max_size" {
  description = "Maximum number of nodes in the managed node group"
  type        = number
  default     = 3
}

variable "node_group_desired_size" {
  description = "Desired number of nodes in the managed node group"
  type        = number
  default     = 2
}

# ── Karpenter ─────────────────────────────────
variable "karpenter_version" {
  description = "Helm chart version for Karpenter"
  type        = string
  default     = "1.4.0"
}

variable "karpenter_namespace" {
  description = "Kubernetes namespace for Karpenter"
  type        = string
  default     = "karpenter"
}

# ── KEDA ──────────────────────────────────────
variable "keda_version" {
  description = "Helm chart version for KEDA"
  type        = string
  default     = "2.16.1"
}

variable "keda_namespace" {
  description = "Kubernetes namespace for KEDA"
  type        = string
  default     = "keda"
}

# ── Observability ─────────────────────────────
variable "monitoring_namespace" {
  description = "Kubernetes namespace for Prometheus and Grafana"
  type        = string
  default     = "monitoring"
}

variable "grafana_admin_password" {
  description = "Admin password for Grafana"
  type        = string
  sensitive   = true
  default     = "admin123!"
}

# ── SQS ───────────────────────────────────────
variable "sqs_queue_names" {
  description = "List of SQS queue names for worker services"
  type        = list(string)
  default     = ["cart-queue", "orders-queue", "checkout-queue"]
}

variable "sqs_visibility_timeout" {
  description = "Visibility timeout in seconds for messages received by consumers"
  type        = number
  default     = 60
}

variable "sqs_message_retention" {
  description = "Message retention period in seconds (default 4 days)"
  type        = number
  default     = 345600
}

# ── ECR ───────────────────────────────────────
variable "ecr_repo_names" {
  description = "List of ECR repository names for backend microservices"
  type        = list(string)
  default     = ["ui", "catalog", "cart", "orders", "checkout", "recommendations"]
}
