variable "ecr_repo_names" {
  description = "List of private ECR repository names to create for backend microservices"
  type        = list(string)
  default     = ["catalog", "cart", "orders", "checkout", "recommendations"]
}

variable "name_prefix" {
  description = "Standard prefix used for resource naming and tagging"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Deployment environment name (e.g. dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "image_tag_mutability" {
  description = "Tag mutability setting for repositories (MUTABLE or IMMUTABLE)"
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "The image_tag_mutability must be either 'MUTABLE' or 'IMMUTABLE'."
  }
}

variable "scan_on_push" {
  description = "Whether images are automatically scanned for vulnerabilities on push"
  type        = bool
  default     = true
}

variable "encryption_type" {
  description = "The encryption type to use for the repository (AES256 or KMS)"
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["AES256", "KMS"], var.encryption_type)
    error_message = "The encryption_type must be either 'AES256' or 'KMS'."
  }
}

variable "kms_key" {
  description = "The ARN of the KMS key to use when encryption_type is KMS"
  type        = string
  default     = null
}

variable "max_image_count" {
  description = "Number of recent tagged images to retain in the repository"
  type        = number
  default     = 10
}

variable "untagged_image_days" {
  description = "Number of days before untagged images are expired by lifecycle policy"
  type        = number
  default     = 7
}

variable "use_name_prefix" {
  description = "Whether to prepend name_prefix to repository names (e.g., prefix/service)"
  type        = bool
  default     = false
}

variable "tags" {
  description = "A map of tags to assign to all created ECR repositories"
  type        = map(string)
  default     = {}
}
