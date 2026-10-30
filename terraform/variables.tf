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
  description = "CIDR blocks for private EKS workload subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "database_subnet_cidrs" {
  description = "CIDR blocks for dedicated RDS private subnets in separate availability zones"
  type        = list(string)
  default     = ["10.0.20.0/24", "10.0.21.0/24"]
}

# ── EKS ──────────────────────────────────────
variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.36"
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

variable "eks_public_access_cidrs" {
  description = "Public IPv4 CIDRs allowed to reach the EKS API; set your current administrator IP as /32"
  type        = list(string)

  validation {
    condition     = length(var.eks_public_access_cidrs) > 0 && alltrue([for cidr in var.eks_public_access_cidrs : can(cidrhost(cidr, 0)) && cidr != "0.0.0.0/0"])
    error_message = "Specify at least one valid public administrator CIDR; 0.0.0.0/0 is not allowed."
  }
}

# ── RDS ──────────────────────────────────────
variable "postgres_engine_version" {
  description = "RDS PostgreSQL engine version"
  type        = string
  default     = "17.11"
}

variable "mysql_engine_version" {
  description = "RDS MySQL engine version"
  type        = string
  default     = "8.4.11"
}

variable "db_instance_class" {
  description = "Class for each Single-AZ RDS instance"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial gp3 storage in GiB per RDS instance"
  type        = number
  default     = 20
}

variable "db_backup_retention_days" {
  description = "Automated RDS backup retention in days"
  type        = number
  default     = 1
}

variable "db_deletion_protection" {
  description = "Enable for databases with data that must survive accidental deletion"
  type        = bool
  default     = false
}

variable "db_create_final_snapshot" {
  description = "Take a final RDS snapshot on destroy instead of discarding demo data"
  type        = bool
  default     = false
}

# ── Karpenter ─────────────────────────────────
variable "karpenter_namespace" {
  description = "Kubernetes namespace for Karpenter"
  type        = string
  default     = "karpenter"
}

# ── KEDA ──────────────────────────────────────
variable "keda_namespace" {
  description = "Kubernetes namespace for KEDA"
  type        = string
  default     = "keda"
}

# ── Cost alert ────────────────────────────────
variable "budget_alert_email" {
  description = "Email for an 80% AWS monthly cost budget alert; null creates the budget without an email notification"
  type        = string
  default     = null
}

variable "monthly_budget_usd" {
  description = "Monthly AWS cost budget in USD; notification requires budget_alert_email"
  type        = number
  default     = 100

  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "monthly_budget_usd must be positive."
  }
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
  default     = ["catalog", "cart", "orders", "checkout", "recommendations", "root"]
}

variable "enable_ecr_push_role" {
  description = "Create the GitHub Actions ECR push role; requires an existing GitHub OIDC provider in this AWS account"
  type        = bool
  default     = false
}

variable "github_oidc_subjects" {
  description = "Exact GitHub OIDC sub claims allowed to push images; match the repository's actual subject format"
  type        = list(string)
  default     = []

  validation {
    condition = !var.enable_ecr_push_role || (length(var.github_oidc_subjects) > 0 && alltrue([
      for subject in var.github_oidc_subjects : startswith(subject, "repo:") && !strcontains(subject, "*") && !strcontains(subject, "?")
    ]))
    error_message = "When enable_ecr_push_role is true, supply explicit repo: GitHub OIDC subjects without wildcards."
  }
}
