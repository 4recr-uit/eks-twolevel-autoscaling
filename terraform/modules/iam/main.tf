locals {
  # The logical queue keys are stable; the ARNs are provided by the SQS module.
  # Each outbox publisher and worker gets its own ServiceAccount and IAM role.
  publisher_service_accounts = {
    for queue_name in keys(var.queue_arns) : queue_name => "${trimsuffix(queue_name, "-queue")}-publisher"
  }
  worker_service_accounts = {
    for queue_name in keys(var.queue_arns) : queue_name => "${trimsuffix(queue_name, "-queue")}-worker"
  }

  # All ECR repository ARNs as a list for policy statements
  ecr_repo_arns_list = values(var.ecr_repo_arns)

  # Shared trust policy for EKS Pod Identity (publishers, workers, KEDA)
  pod_identity_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "pods.eks.amazonaws.com"
      }
      Action = [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
    }]
  })
}

# 1. OUTBOX PUBLISHERS — one Pod Identity role per main queue

resource "aws_iam_role" "publisher" {
  for_each = var.queue_arns

  name               = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-publisher-role"
  description        = "Pod Identity role for ${each.key} outbox publisher"
  assume_role_policy = local.pod_identity_trust_policy

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-publisher-role"
    PodRole = local.publisher_service_accounts[each.key]
  })
}

data "aws_iam_policy_document" "publisher_sqs" {
  for_each = var.queue_arns

  statement {
    sid       = "PublishToOwnQueue"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [each.value]
  }
}

resource "aws_iam_policy" "publisher_sqs" {
  for_each = var.queue_arns

  name        = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-publisher-sqs"
  description = "Allows ${each.key} publisher to send only to its main queue"
  policy      = data.aws_iam_policy_document.publisher_sqs[each.key].json

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-publisher-sqs"
    PodRole = local.publisher_service_accounts[each.key]
  })
}

resource "aws_iam_role_policy_attachment" "publisher_sqs" {
  for_each = var.queue_arns

  role       = aws_iam_role.publisher[each.key].name
  policy_arn = aws_iam_policy.publisher_sqs[each.key].arn
}

# Each association may be created before its Kubernetes ServiceAccount exists.
resource "aws_eks_pod_identity_association" "publisher" {
  for_each = var.queue_arns

  cluster_name    = var.cluster_name
  namespace       = var.app_namespace
  service_account = local.publisher_service_accounts[each.key]
  role_arn        = aws_iam_role.publisher[each.key].arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-publisher-pod-identity"
  })
}

# 2. WORKERS — one Pod Identity role per main queue, no DLQ access

resource "aws_iam_role" "worker" {
  for_each = var.queue_arns

  name               = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-worker-role"
  description        = "Pod Identity role for ${each.key} worker"
  assume_role_policy = local.pod_identity_trust_policy

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-worker-role"
    PodRole = local.worker_service_accounts[each.key]
  })
}

data "aws_iam_policy_document" "worker_sqs" {
  for_each = var.queue_arns

  statement {
    sid    = "ConsumeOwnQueue"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    resources = [each.value]
  }
}

resource "aws_iam_policy" "worker_sqs" {
  for_each = var.queue_arns

  name        = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-worker-sqs"
  description = "Allows ${each.key} worker to consume only its main queue"
  policy      = data.aws_iam_policy_document.worker_sqs[each.key].json

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-worker-sqs"
    PodRole = local.worker_service_accounts[each.key]
  })
}

resource "aws_iam_role_policy_attachment" "worker_sqs" {
  for_each = var.queue_arns

  role       = aws_iam_role.worker[each.key].name
  policy_arn = aws_iam_policy.worker_sqs[each.key].arn
}

resource "aws_eks_pod_identity_association" "worker" {
  for_each = var.queue_arns

  cluster_name    = var.cluster_name
  namespace       = var.app_namespace
  service_account = local.worker_service_accounts[each.key]
  role_arn        = aws_iam_role.worker[each.key].arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-${trimsuffix(each.key, "-queue")}-worker-pod-identity"
  })
}

# 3. KEDA OPERATOR — SQS GetQueueAttributes (read-only metric polling)

resource "aws_iam_role" "keda" {
  name               = "${var.name_prefix}-keda-role"
  description        = "EKS Pod Identity role for the KEDA operator. Read-only access to SQS queue attributes for autoscaling decisions."
  assume_role_policy = local.pod_identity_trust_policy

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-keda-role"
    PodRole = "keda-operator"
  })
}

data "aws_iam_policy_document" "keda_sqs" {
  statement {
    sid    = "KEDASQSReadOnly"
    effect = "Allow"
    actions = [
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    # KEDA only needs to read queue depth from main queues — not DLQs
    resources = values(var.queue_arns)
  }
}

resource "aws_iam_policy" "keda_sqs" {
  name        = "${var.name_prefix}-keda-sqs-policy"
  description = "Allows KEDA operator to read SQS queue attributes for autoscaling metric computation (read-only, least privilege)"
  policy      = data.aws_iam_policy_document.keda_sqs.json

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-keda-sqs-policy"
    PodRole = "keda-operator"
  })
}

resource "aws_iam_role_policy_attachment" "keda_sqs" {
  role       = aws_iam_role.keda.name
  policy_arn = aws_iam_policy.keda_sqs.arn
}

# Pod Identity Association: maps keda-operator ServiceAccount → IAM Role
resource "aws_eks_pod_identity_association" "keda" {
  cluster_name    = var.cluster_name
  namespace       = var.keda_namespace
  service_account = var.keda_service_account
  role_arn        = aws_iam_role.keda.arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-keda-pod-identity"
  })
}

# 4. ECR PUSH — GitHub Actions CI/CD (optional)

data "aws_iam_policy_document" "ecr_push_trust" {
  count = var.enable_ecr_push_role ? 1 : 0

  statement {
    sid     = "GitHubActionsOIDC"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = var.github_oidc_subjects
    }
  }
}

resource "aws_iam_role" "ecr_push" {
  count = var.enable_ecr_push_role ? 1 : 0

  name               = "${var.name_prefix}-ecr-push-role"
  description        = "Role assumed by GitHub Actions CI/CD pipeline to push Docker images to ECR"
  assume_role_policy = data.aws_iam_policy_document.ecr_push_trust[0].json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-ecr-push-role"
  })
}

data "aws_iam_policy_document" "ecr_push" {
  count = var.enable_ecr_push_role ? 1 : 0

  statement {
    sid    = "ECRAuthToken"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken"
    ]
    # GetAuthorizationToken is global — must be * resource
    resources = ["*"]
  }

  statement {
    sid    = "ECRPushImages"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
    ]
    # Scoped to only the repositories provisioned by this project
    resources = local.ecr_repo_arns_list
  }
}

resource "aws_iam_policy" "ecr_push" {
  count = var.enable_ecr_push_role ? 1 : 0

  name        = "${var.name_prefix}-ecr-push-policy"
  description = "Allows CI/CD pipeline to push Docker images to the project ECR repositories"
  policy      = data.aws_iam_policy_document.ecr_push[0].json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-ecr-push-policy"
  })
}

resource "aws_iam_role_policy_attachment" "ecr_push" {
  count = var.enable_ecr_push_role ? 1 : 0

  role       = aws_iam_role.ecr_push[0].name
  policy_arn = aws_iam_policy.ecr_push[0].arn
}

# ── Data Sources ──────────────────────────────────────────
data "aws_caller_identity" "current" {}
