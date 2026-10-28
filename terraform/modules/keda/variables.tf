variable "keda_version" {
  description = "Version of the official KEDA Helm chart"
  type        = string
}

variable "keda_namespace" {
  description = "Namespace where the KEDA operator runs"
  type        = string
}

variable "app_namespace" {
  description = "Namespace containing the three worker Deployments"
  type        = string
}

variable "aws_region" {
  description = "AWS Region of the SQS queues"
  type        = string
}

variable "queue_urls" {
  description = "SQS queue URLs keyed by logical queue name"
  type        = map(string)
}

variable "worker_deployments" {
  description = "Map of SQS logical queue names to worker Deployment names"
  type        = map(string)
}

variable "enable_scaled_objects" {
  description = "Create ScaledObjects only after the app namespace and worker Deployments exist"
  type        = bool
  default     = false
}

variable "queue_length" {
  description = "Target number of SQS messages per worker replica"
  type        = number
  default     = 10

  validation {
    condition     = var.queue_length >= 1
    error_message = "queue_length must be at least 1."
  }
}

variable "min_replica_count" {
  description = "Minimum worker replicas; use 0 for scale-to-zero and 1 for the HPA comparison"
  type        = number
  default     = 0

  validation {
    condition     = var.min_replica_count >= 0
    error_message = "min_replica_count cannot be negative."
  }
}

variable "max_replica_count" {
  description = "Maximum worker replicas per Deployment"
  type        = number
  default     = 10

  validation {
    condition     = var.max_replica_count >= 1 && var.max_replica_count > var.min_replica_count
    error_message = "max_replica_count must exceed min_replica_count."
  }
}

variable "polling_interval" {
  description = "Seconds between SQS polling attempts"
  type        = number
  default     = 30

  validation {
    condition     = var.polling_interval >= 1
    error_message = "polling_interval must be at least 1 second."
  }
}

variable "cooldown_period" {
  description = "Seconds KEDA waits before scaling inactive workers to zero"
  type        = number
  default     = 300

  validation {
    condition     = var.cooldown_period >= 0
    error_message = "cooldown_period cannot be negative."
  }
}
