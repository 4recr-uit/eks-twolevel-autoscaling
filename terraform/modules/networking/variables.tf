variable "name_prefix" {
  description = "Prefix for naming resources"
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name (used for subnet tags for EKS and Karpenter discovery)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "availability_zones" {
  description = "List of availability zones for subnets"
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) >= 2 && length(distinct(var.availability_zones)) == length(var.availability_zones)
    error_message = "Provide at least two distinct availability zones for EKS and RDS subnet placement."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) == length(var.availability_zones) && alltrue([for cidr in var.public_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "Provide one valid public subnet CIDR per availability zone."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for EKS workload private subnets"
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_cidrs) == length(var.availability_zones) && alltrue([for cidr in var.private_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "Provide one valid workload private subnet CIDR per availability zone."
  }
}

variable "database_subnet_cidrs" {
  description = "CIDR blocks for isolated RDS private subnets, one in each availability zone"
  type        = list(string)

  validation {
    condition     = length(var.database_subnet_cidrs) == length(var.availability_zones) && alltrue([for cidr in var.database_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "Provide one valid database subnet CIDR per availability zone."
  }
}
