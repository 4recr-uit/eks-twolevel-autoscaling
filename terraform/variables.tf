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
variable "karpenter_version" {
  description = "Helm chart version for Karpenter"
  type        = string
  default     = "1.15.0"
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
  default     = "2.21.0"
}

variable "keda_namespace" {
  description = "Kubernetes namespace for KEDA"
  type        = string
  default     = "keda"
}

variable "enable_cluster_addons" {
  description = "Install Karpenter and KEDA after the EKS cluster exists; false for the first AWS-only apply"
  type        = bool
  default     = false
}

variable "enable_keda_scaled_objects" {
  description = "Create SQS ScaledObjects after the three worker Deployments and retailstore namespace exist"
  type        = bool
  default     = false
}

variable "keda_queue_length" {
  description = "Target SQS backlog per worker replica"
  type        = number
  default     = 10

  validation {
    condition     = var.keda_queue_length >= 1
    error_message = "keda_queue_length must be at least 1."
  }
}

variable "keda_min_replica_count" {
  description = "Minimum worker replicas for KEDA (0 for scale-to-zero, 1 for HPA comparison)"
  type        = number
  default     = 0

  validation {
    condition     = var.keda_min_replica_count >= 0
    error_message = "keda_min_replica_count cannot be negative."
  }
}

variable "keda_max_replica_count" {
  description = "Maximum replicas for each KEDA managed worker Deployment"
  type        = number
  default     = 10

  validation {
    condition     = var.keda_max_replica_count >= 1
    error_message = "keda_max_replica_count must be at least 1."
  }
}

variable "keda_polling_interval" {
  description = "Seconds between KEDA SQS polls"
  type        = number
  default     = 30

  validation {
    condition     = var.keda_polling_interval >= 1
    error_message = "keda_polling_interval must be at least 1 second."
  }
}

variable "keda_cooldown_period" {
  description = "Seconds before KEDA scales inactive workers to zero"
  type        = number
  default     = 300

  validation {
    condition     = var.keda_cooldown_period >= 0
    error_message = "keda_cooldown_period cannot be negative."
  }
}

# ── Observability ─────────────────────────────
variable "monitoring_namespace" {
  description = "Kubernetes namespace for Prometheus and Grafana"
  type        = string
  default     = "monitoring"
}

variable "enable_observability" {
  description = "Install private Prometheus/Grafana stack during the measurement phase"
  type        = bool
  default     = false
}

variable "monitoring_chart_version" {
  description = "Pinned kube-prometheus-stack chart version"
  type        = string
  default     = "92.7.0"
}

variable "grafana_admin_secret_name" {
  description = "Pre-existing Kubernetes Secret with admin-user and admin-password keys"
  type        = string
  default     = "grafana-admin"
}

variable "grafana_admin_password" {
  description = "Deprecated, unused: create grafana_admin_secret_name in Kubernetes instead to keep the password out of Terraform state"
  type        = string
  sensitive   = true
  default     = null
}

variable "budget_alert_email" {
  description = "Email for an 80% AWS monthly cost budget alert; null creates the budget without an email notification"
  type        = string
  default     = null
}

variable "monthly_budget_usd" {
  description = "Monthly AWS budget limit in USD when budget_alert_email is set"
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
  default     = ["catalog", "cart", "orders", "checkout", "recommendations"]
}
