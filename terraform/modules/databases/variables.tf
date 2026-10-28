variable "name_prefix" {
  description = "Prefix for RDS resources"
  type        = string
}

variable "vpc_id" {
  description = "VPC containing EKS and RDS"
  type        = string
}

variable "database_subnet_ids" {
  description = "Isolated database subnets in at least two availability zones"
  type        = list(string)

  validation {
    condition     = length(var.database_subnet_ids) >= 2
    error_message = "RDS requires database subnets in at least two availability zones."
  }
}

variable "node_security_group_id" {
  description = "Security group attached to both seed and Karpenter nodes"
  type        = string
}

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
  description = "Instance class for both Single-AZ databases"
  type        = string
  default     = "db.t4g.micro"
}

variable "master_username" {
  description = "Bootstrap administrator username; RDS manages its password in Secrets Manager"
  type        = string
  default     = "dbadmin"
}

variable "allocated_storage" {
  description = "Initial gp3 storage per database in GiB"
  type        = number
  default     = 20

  validation {
    condition     = var.allocated_storage >= 20
    error_message = "allocated_storage must be at least 20 GiB."
  }
}

variable "max_allocated_storage" {
  description = "Storage autoscaling cap per database in GiB; 0 disables autoscaling"
  type        = number
  default     = 0
}

variable "backup_retention_days" {
  description = "Automated backup retention in days"
  type        = number
  default     = 1

  validation {
    condition     = var.backup_retention_days >= 0 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 0 and 35."
  }
}

variable "deletion_protection" {
  description = "Protect RDS instances from deletion; enable when data must be retained"
  type        = bool
  default     = false
}

variable "create_final_snapshot" {
  description = "Create final snapshots during destroy; snapshot identifiers must be unique"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Common AWS tags"
  type        = map(string)
  default     = {}
}
