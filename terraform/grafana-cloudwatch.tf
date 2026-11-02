# Grafana reads CloudWatch metrics through EKS Pod Identity; no AWS keys in Kubernetes.
data "aws_iam_policy_document" "grafana_pod_identity_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/eks-cluster-name"
      values   = [local.cluster_name]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes-namespace"
      values   = [local.namespaces.monitoring]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes-service-account"
      values   = ["monitoring-grafana"]
    }
  }
}

resource "aws_iam_role" "grafana_cloudwatch" {
  name               = "${local.name_prefix}-grafana-cloudwatch-role"
  description        = "CloudWatch metrics read access for Grafana via EKS Pod Identity"
  assume_role_policy = data.aws_iam_policy_document.grafana_pod_identity_trust.json
}

resource "aws_iam_role_policy" "grafana_cloudwatch" {
  name = "cloudwatch-metrics-read"
  role = aws_iam_role.grafana_cloudwatch.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["cloudwatch:GetMetricData", "cloudwatch:ListMetrics"]
      Resource = "*"
    }]
  })
}

resource "aws_eks_pod_identity_association" "grafana_cloudwatch" {
  cluster_name    = module.eks.cluster_name
  namespace       = local.namespaces.monitoring
  service_account = "monitoring-grafana"
  role_arn        = aws_iam_role.grafana_cloudwatch.arn
}
