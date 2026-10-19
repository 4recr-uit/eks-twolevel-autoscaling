locals {
  # Flatten all SQS ARNs (main queues + DLQs) into a single list
  # used by the worker policy — worker needs access to both
  all_sqs_arns = concat(
    values(var.queue_arns),
    values(var.dlq_arns)
  )

  # All ECR repository ARNs as a list for policy statements
  ecr_repo_arns_list = values(var.ecr_repo_arns)

  # Shared trust policy for EKS Pod Identity (same for producer, worker, keda)
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

# 1. PRODUCER-API — SQS SendMessage

resource "aws_iam_role" "producer" {
  name               = "${var.name_prefix}-producer-role"
  description        = "EKS Pod Identity role for the producer-api service. Grants SQS SendMessage on all worker queues."
  assume_role_policy = local.pod_identity_trust_policy

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-producer-role"
    PodRole = "producer-api"
  })
}

data "aws_iam_policy_document" "producer_sqs" {
  statement {
    sid    = "ProducerSQSSend"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    # Scope to main queues only — producer never touches DLQs
    resources = values(var.queue_arns)
  }
}

resource "aws_iam_policy" "producer_sqs" {
  name        = "${var.name_prefix}-producer-sqs-policy"
  description = "Allows producer-api to send messages to SQS worker queues"
  policy      = data.aws_iam_policy_document.producer_sqs.json

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-producer-sqs-policy"
    PodRole = "producer-api"
  })
}

resource "aws_iam_role_policy_attachment" "producer_sqs" {
  role       = aws_iam_role.producer.name
  policy_arn = aws_iam_policy.producer_sqs.arn
}

# Pod Identity Association: maps producer-api ServiceAccount → IAM Role
resource "aws_eks_pod_identity_association" "producer" {
  cluster_name    = var.cluster_name
  namespace       = var.app_namespace
  service_account = var.producer_service_account
  role_arn        = aws_iam_role.producer.arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-producer-pod-identity"
  })
}

# 2. WORKER — SQS ReceiveMessage, DeleteMessage, ChangeMessageVisibility

resource "aws_iam_role" "worker" {
  name               = "${var.name_prefix}-worker-role"
  description        = "EKS Pod Identity role for the worker service. Grants SQS receive, delete, and visibility timeout changes on worker queues and DLQs."
  assume_role_policy = local.pod_identity_trust_policy

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-worker-role"
    PodRole = "worker"
  })
}

data "aws_iam_policy_document" "worker_sqs" {
  statement {
    sid    = "WorkerSQSConsume"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    # Worker has access to both main queues and DLQs
    # (DLQ access allows manual inspection and re-drive during debugging)
    resources = local.all_sqs_arns
  }
}

resource "aws_iam_policy" "worker_sqs" {
  name        = "${var.name_prefix}-worker-sqs-policy"
  description = "Allows worker pods to consume, delete, and manage message visibility in SQS queues and DLQs"
  policy      = data.aws_iam_policy_document.worker_sqs.json

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-worker-sqs-policy"
    PodRole = "worker"
  })
}

resource "aws_iam_role_policy_attachment" "worker_sqs" {
  role       = aws_iam_role.worker.name
  policy_arn = aws_iam_policy.worker_sqs.arn
}

# Pod Identity Association: maps worker ServiceAccount → IAM Role
resource "aws_eks_pod_identity_association" "worker" {
  cluster_name    = var.cluster_name
  namespace       = var.app_namespace
  service_account = var.worker_service_account
  role_arn        = aws_iam_role.worker.arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-worker-pod-identity"
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
