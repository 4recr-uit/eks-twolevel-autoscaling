# ── Queue Names ───────────────────────────────
variable "sqs_queue_names" {
  description = "List of SQS queue names to create for worker services"
  type        = list(string)
  default     = ["cart-queue", "orders-queue", "checkout-queue"]
}

# ── Naming & Tagging ──────────────────────────
variable "name_prefix" {
  description = "Standard prefix used for resource naming and tagging"
  type        = string
  default     = ""
}

variable "use_name_prefix" {
  description = "Whether to prepend name_prefix to queue names (e.g., prefix-cart-queue)"
  type        = bool
  default     = false
}

variable "environment" {
  description = "Deployment environment name (e.g. dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "tags" {
  description = "A map of tags to assign to all created SQS queues"
  type        = map(string)
  default     = {}
}

# ── Queue Configuration ───────────────────────
variable "sqs_visibility_timeout" {
  description = "Visibility timeout in seconds for messages received by consumers (1–43200)"
  type        = number
  default     = 60

  validation {
    condition     = var.sqs_visibility_timeout >= 1 && var.sqs_visibility_timeout <= 43200
    error_message = "sqs_visibility_timeout must be between 1 and 43200 seconds."
  }
}

variable "sqs_message_retention" {
  description = "Message retention period in seconds (60–1209600). Default is 4 days (345600)."
  type        = number
  default     = 345600

  validation {
    condition     = var.sqs_message_retention >= 60 && var.sqs_message_retention <= 1209600
    error_message = "sqs_message_retention must be between 60 and 1209600 seconds."
  }
}

variable "receive_wait_time_seconds" {
  description = "Wait time in seconds for long polling (0–20). Set to 20 to reduce API costs."
  type        = number
  default     = 20

  validation {
    condition     = var.receive_wait_time_seconds >= 0 && var.receive_wait_time_seconds <= 20
    error_message = "receive_wait_time_seconds must be between 0 and 20."
  }
}

variable "max_message_size" {
  description = "Maximum size of a message in bytes (1024–262144). Default is 256 KB."
  type        = number
  default     = 262144
}

# ── Dead Letter Queue (DLQ) ───────────────────
variable "enable_dlq" {
  description = "Whether to create a Dead Letter Queue for each main queue"
  type        = bool
  default     = true
}

variable "max_receive_count" {
  description = "Number of times a message can be received before being sent to the DLQ"
  type        = number
  default     = 3

  validation {
    condition     = var.max_receive_count >= 1 && var.max_receive_count <= 1000
    error_message = "max_receive_count must be between 1 and 1000."
  }
}

variable "dlq_message_retention" {
  description = "Message retention period in seconds for DLQs (14 days = 1209600)"
  type        = number
  default     = 1209600
}
