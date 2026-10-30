# ── Data Sources ───────────────────────────────────────────────────────────────
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

# ─────────────────────────────────────────────────────────────────────────────
# Group A: Interruption Handling (SQS & EventBridge Rules)
# Enables graceful node drain upon Spot interruptions, rebalance recommendations,
# instance state changes, or scheduled AWS health maintenance events.
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_sqs_queue" "interruption" {
  name                      = "${var.cluster_name}-karpenter"
  message_retention_seconds = 300
  sqs_managed_sse_enabled   = true

  tags = merge(
    var.tags,
    {
      Name = "${var.cluster_name}-karpenter-interruption"
    }
  )
}

resource "aws_sqs_queue_policy" "interruption" {
  queue_url = aws_sqs_queue.interruption.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowEventBridgeToQueue"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.interruption.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = [
              aws_cloudwatch_event_rule.spot_interruption.arn,
              aws_cloudwatch_event_rule.rebalance.arn,
              aws_cloudwatch_event_rule.instance_state_change.arn,
              aws_cloudwatch_event_rule.health_event.arn,
            ]
          }
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "sqs:*"
        Resource  = aws_sqs_queue.interruption.arn
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# 1. Spot Instance Interruption Warning
resource "aws_cloudwatch_event_rule" "spot_interruption" {
  name        = "${var.name_prefix}-karpenter-spot-interruption"
  description = "Capture EC2 Spot instance interruption warnings for Karpenter"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Spot Instance Interruption Warning"]
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "spot_interruption" {
  rule      = aws_cloudwatch_event_rule.spot_interruption.name
  target_id = "KarpenterInterruptionQueueSpot"
  arn       = aws_sqs_queue.interruption.arn
}

# 2. EC2 Instance Rebalance Recommendation
resource "aws_cloudwatch_event_rule" "rebalance" {
  name        = "${var.name_prefix}-karpenter-rebalance"
  description = "Capture EC2 Instance rebalance recommendations for Karpenter"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance Rebalance Recommendation"]
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "rebalance" {
  rule      = aws_cloudwatch_event_rule.rebalance.name
  target_id = "KarpenterInterruptionQueueRebalance"
  arn       = aws_sqs_queue.interruption.arn
}

# 3. EC2 Instance State-change Notification
resource "aws_cloudwatch_event_rule" "instance_state_change" {
  name        = "${var.name_prefix}-karpenter-instance-state"
  description = "Capture EC2 Instance state-change notifications for Karpenter"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance State-change Notification"]
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "instance_state_change" {
  rule      = aws_cloudwatch_event_rule.instance_state_change.name
  target_id = "KarpenterInterruptionQueueInstanceState"
  arn       = aws_sqs_queue.interruption.arn
}

# 4. AWS Health Scheduled Event
resource "aws_cloudwatch_event_rule" "health_event" {
  name        = "${var.name_prefix}-karpenter-health"
  description = "Capture AWS Health events for Karpenter"

  event_pattern = jsonencode({
    source      = ["aws.health"]
    detail-type = ["AWS Health Event"]
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "health_event" {
  rule      = aws_cloudwatch_event_rule.health_event.name
  target_id = "KarpenterInterruptionQueueHealth"
  arn       = aws_sqs_queue.interruption.arn
}

# ─────────────────────────────────────────────────────────────────────────────
# Group B: Dedicated IAM Role for Karpenter Nodes
# The seed Managed Node Group keeps its own role in the EKS module. Karpenter
# nodes use this role through EC2NodeClass and an EC2_LINUX EKS access entry.
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "node" {
  name        = "${var.name_prefix}-karpenter-node-role"
  description = "EC2 node role used only by Karpenter-managed nodes"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-karpenter-node-role"
  })
}

# Match the node policies in the Karpenter 1.15 reference. The VPC CNI still
# uses the node role because its own Pod Identity role is not configured yet.
resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "AmazonEKS_CNI_Policy",
    "AmazonEKSWorkerNodePolicy",
    "AmazonEC2ContainerRegistryPullOnly",
    "AmazonSSMManagedInstanceCore",
  ])

  role       = aws_iam_role.node.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/${each.value}"
}

# ─────────────────────────────────────────────────────────────────────────────
# Group C: Controller IAM Role & Access Entry (AWS Resources)
# Grants Karpenter controller permissions to manage EC2 instances, pass its
# dedicated node IAM role, and access the interruption queue. Uses Pod Identity.
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "controller" {
  name        = "${var.name_prefix}-karpenter-controller"
  description = "IAM Role for Karpenter Controller in EKS cluster ${var.cluster_name}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowPodIdentity"
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

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-karpenter-controller"
    }
  )
}


# Bind Karpenter controller role to the Kubernetes ServiceAccount via EKS Pod Identity
resource "aws_eks_pod_identity_association" "karpenter" {
  cluster_name    = var.cluster_name
  namespace       = var.karpenter_namespace
  service_account = var.service_account_name
  role_arn        = aws_iam_role.controller.arn
}

# Register only Karpenter's self-managed node role; EKS manages seed-node auth.
resource "aws_eks_access_entry" "karpenter_node" {
  cluster_name  = var.cluster_name
  principal_arn = aws_iam_role.node.arn
  type          = "EC2_LINUX"

  depends_on = [aws_iam_role_policy_attachment.node]
}
