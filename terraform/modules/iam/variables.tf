# ── Identifiers & Naming ──────────────────────
variable "name_prefix" {
  description = "Prefix applied to all IAM resources"
  type        = string
}

# ── EKS Cluster (for Pod Identity Associations) ───────────
variable "cluster_name" {
  description = "Name of the EKS cluster — required for Pod Identity Association resources"
  type        = string
}

# ── Kubernetes Namespaces & Service Accounts ──────────────
variable "app_namespace" {
  description = "Kubernetes namespace where producer and worker pods run"
  type        = string
  default     = "retailstore"
}

variable "keda_namespace" {
  description = "Kubernetes namespace where KEDA operator runs"
  type        = string
  default     = "keda"
}

variable "producer_service_account" {
  description = "Kubernetes Service Account name for the producer-api pod"
  type        = string
  default     = "producer-api"
}

variable "worker_service_account" {
  description = "Kubernetes Service Account name for the worker pod"
  type        = string
  default     = "worker"
}

variable "keda_service_account" {
  description = "Kubernetes Service Account name for the KEDA operator"
  type        = string
  default     = "keda-operator"
}

# ── SQS Queue ARNs (from module "sqs") ───────────────────
variable "queue_arns" {
  description = "Map of queue logical names to their SQS queue ARNs (from module sqs)"
  type        = map(string)
}

variable "dlq_arns" {
  description = "Map of queue logical names to their Dead Letter Queue ARNs (from module sqs)"
  type        = map(string)
  default     = {}
}

# ── ECR Repository ARNs (from module "ecr") ──────────────
variable "ecr_repo_arns" {
  description = "Map of service names to ECR repository ARNs (from module ecr)"
  type        = map(string)
}

# ── ECR Push Role (optional — for CI/CD) ─────────────────
variable "enable_ecr_push_role" {
  description = "If true, create an IAM role allowing external systems (e.g. GitHub Actions) to push Docker images to ECR"
  type        = bool
  default     = false
}

variable "github_oidc_subjects" {
  description = "List of GitHub OIDC subjects allowed to assume the ECR push role (e.g. repo:ORG/REPO:ref:refs/heads/main). Required when enable_ecr_push_role = true"
  type        = list(string)
  default     = []
}

# ── Tagging ───────────────────────────────────────────────
variable "tags" {
  description = "Common tags applied to all IAM resources"
  type        = map(string)
  default     = {}
}
