locals {
  # Filter out empty or whitespace-only repository names
  valid_repo_names = toset([
    for name in var.ecr_repo_names : trimspace(name) if trimspace(name) != ""
  ])
}

resource "aws_ecr_repository" "this" {
  for_each = local.valid_repo_names

  name                 = var.use_name_prefix && var.name_prefix != "" ? "${var.name_prefix}/${each.value}" : each.value
  image_tag_mutability = var.image_tag_mutability

  encryption_configuration {
    encryption_type = var.encryption_type
    kms_key         = var.kms_key
  }

  image_scanning_configuration {
    scan_on_push = var.scan_on_push
  }

  tags = merge(
    {
      Environment = var.environment
    },
    var.tags,
    {
      Name = var.name_prefix != "" ? "${var.name_prefix}-${each.value}" : each.value
    }
  )
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than ${var.untagged_image_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_image_days
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Retain the last ${var.max_image_count} images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.max_image_count
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
