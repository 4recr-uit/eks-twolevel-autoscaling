# Controller permissions follow the Karpenter AWS provider v1.15.0
# CloudFormation reference. Keep the policy groups separate to stay within
# the IAM managed-policy document size limit and to make upgrades reviewable.
locals {
  ec2_arn_prefix       = "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.region}"
  instance_profile_arn = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:instance-profile/*"
  cluster_arn          = "arn:${data.aws_partition.current.partition}:eks:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:cluster/${var.cluster_name}"

  controller_policy_documents = {
    node_lifecycle = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid    = "AllowScopedEC2InstanceAccessActions"
          Effect = "Allow"
          Resource = [
            "${local.ec2_arn_prefix}::image/*",
            "${local.ec2_arn_prefix}::snapshot/*",
            "${local.ec2_arn_prefix}:*:security-group/*",
            "${local.ec2_arn_prefix}:*:subnet/*",
            "${local.ec2_arn_prefix}:*:capacity-reservation/*",
            "${local.ec2_arn_prefix}:*:placement-group/*"
          ]
          Action = ["ec2:RunInstances", "ec2:CreateFleet"]
        },
        {
          Sid      = "AllowScopedEC2LaunchTemplateAccessActions"
          Effect   = "Allow"
          Resource = "${local.ec2_arn_prefix}:*:launch-template/*"
          Action   = ["ec2:RunInstances", "ec2:CreateFleet"]
          Condition = {
            StringEquals = {
              "aws:ResourceTag/kubernetes.io/cluster/${var.cluster_name}" = "owned"
            }
            StringLike = {
              "aws:ResourceTag/karpenter.sh/nodepool" = "*"
            }
          }
        },
        {
          Sid    = "AllowScopedEC2InstanceActionsWithTags"
          Effect = "Allow"
          Resource = [
            "${local.ec2_arn_prefix}:*:fleet/*",
            "${local.ec2_arn_prefix}:*:instance/*",
            "${local.ec2_arn_prefix}:*:volume/*",
            "${local.ec2_arn_prefix}:*:network-interface/*",
            "${local.ec2_arn_prefix}:*:launch-template/*",
            "${local.ec2_arn_prefix}:*:spot-instances-request/*"
          ]
          Action = ["ec2:RunInstances", "ec2:CreateFleet", "ec2:CreateLaunchTemplate"]
          Condition = {
            StringEquals = {
              "aws:RequestTag/kubernetes.io/cluster/${var.cluster_name}" = "owned"
              "aws:RequestTag/eks:eks-cluster-name"                      = var.cluster_name
            }
            StringLike = {
              "aws:RequestTag/karpenter.sh/nodepool" = "*"
            }
          }
        },
        {
          Sid    = "AllowScopedResourceCreationTagging"
          Effect = "Allow"
          Resource = [
            "${local.ec2_arn_prefix}:*:fleet/*",
            "${local.ec2_arn_prefix}:*:instance/*",
            "${local.ec2_arn_prefix}:*:volume/*",
            "${local.ec2_arn_prefix}:*:network-interface/*",
            "${local.ec2_arn_prefix}:*:launch-template/*",
            "${local.ec2_arn_prefix}:*:spot-instances-request/*"
          ]
          Action = "ec2:CreateTags"
          Condition = {
            StringEquals = {
              "aws:RequestTag/kubernetes.io/cluster/${var.cluster_name}" = "owned"
              "aws:RequestTag/eks:eks-cluster-name"                      = var.cluster_name
              "ec2:CreateAction"                                         = ["RunInstances", "CreateFleet", "CreateLaunchTemplate"]
            }
            StringLike = {
              "aws:RequestTag/karpenter.sh/nodepool" = "*"
            }
          }
        },
        {
          Sid      = "AllowScopedResourceTagging"
          Effect   = "Allow"
          Resource = "${local.ec2_arn_prefix}:*:instance/*"
          Action   = "ec2:CreateTags"
          Condition = {
            StringEquals = {
              "aws:ResourceTag/kubernetes.io/cluster/${var.cluster_name}" = "owned"
            }
            StringLike = {
              "aws:ResourceTag/karpenter.sh/nodepool" = "*"
            }
            StringEqualsIfExists = {
              "aws:RequestTag/eks:eks-cluster-name" = var.cluster_name
            }
            "ForAllValues:StringEquals" = {
              "aws:TagKeys" = ["eks:eks-cluster-name", "karpenter.sh/nodeclaim", "Name"]
            }
          }
        },
        {
          Sid    = "AllowScopedDeletion"
          Effect = "Allow"
          Resource = [
            "${local.ec2_arn_prefix}:*:instance/*",
            "${local.ec2_arn_prefix}:*:launch-template/*"
          ]
          Action = ["ec2:TerminateInstances", "ec2:RebootInstances", "ec2:DeleteLaunchTemplate"]
          Condition = {
            StringEquals = {
              "aws:ResourceTag/kubernetes.io/cluster/${var.cluster_name}" = "owned"
            }
            StringLike = {
              "aws:ResourceTag/karpenter.sh/nodepool" = "*"
            }
          }
        }
      ]
    })

    iam_integration = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "AllowPassingInstanceRole"
          Effect   = "Allow"
          Resource = aws_iam_role.node.arn
          Action   = "iam:PassRole"
          Condition = {
            StringEquals = {
              "iam:PassedToService" = ["ec2.amazonaws.com", "ec2.amazonaws.com.cn"]
            }
          }
        },
        {
          Sid      = "AllowScopedInstanceProfileCreationActions"
          Effect   = "Allow"
          Resource = local.instance_profile_arn
          Action   = "iam:CreateInstanceProfile"
          Condition = {
            StringEquals = {
              "aws:RequestTag/kubernetes.io/cluster/${var.cluster_name}" = "owned"
              "aws:RequestTag/eks:eks-cluster-name"                      = var.cluster_name
              "aws:RequestTag/topology.kubernetes.io/region"             = data.aws_region.current.region
            }
            StringLike = {
              "aws:RequestTag/karpenter.k8s.aws/ec2nodeclass" = "*"
            }
          }
        },
        {
          Sid      = "AllowScopedInstanceProfileTagActions"
          Effect   = "Allow"
          Resource = local.instance_profile_arn
          Action   = "iam:TagInstanceProfile"
          Condition = {
            StringEquals = {
              "aws:ResourceTag/kubernetes.io/cluster/${var.cluster_name}" = "owned"
              "aws:ResourceTag/topology.kubernetes.io/region"             = data.aws_region.current.region
              "aws:RequestTag/kubernetes.io/cluster/${var.cluster_name}"  = "owned"
              "aws:RequestTag/eks:eks-cluster-name"                       = var.cluster_name
              "aws:RequestTag/topology.kubernetes.io/region"              = data.aws_region.current.region
            }
            StringLike = {
              "aws:ResourceTag/karpenter.k8s.aws/ec2nodeclass" = "*"
              "aws:RequestTag/karpenter.k8s.aws/ec2nodeclass"  = "*"
            }
          }
        },
        {
          Sid      = "AllowScopedInstanceProfileActions"
          Effect   = "Allow"
          Resource = local.instance_profile_arn
          Action   = ["iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile", "iam:DeleteInstanceProfile"]
          Condition = {
            StringEquals = {
              "aws:ResourceTag/kubernetes.io/cluster/${var.cluster_name}" = "owned"
              "aws:ResourceTag/topology.kubernetes.io/region"             = data.aws_region.current.region
            }
            StringLike = {
              "aws:ResourceTag/karpenter.k8s.aws/ec2nodeclass" = "*"
            }
          }
        }
      ]
    })

    eks_integration = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid      = "AllowAPIServerEndpointDiscovery"
        Effect   = "Allow"
        Resource = local.cluster_arn
        Action   = "eks:DescribeCluster"
      }]
    })

    interruption = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid      = "AllowInterruptionQueueActions"
        Effect   = "Allow"
        Resource = aws_sqs_queue.interruption.arn
        Action   = ["sqs:DeleteMessage", "sqs:GetQueueUrl", "sqs:ReceiveMessage"]
      }]
    })

    zonal_shift = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid      = "AllowZonalShiftStatusReadOnly"
        Effect   = "Allow"
        Resource = "*"
        Action   = "arc-zonal-shift:GetManagedResource"
        Condition = {
          StringEquals = {
            "arc-zonal-shift:ResourceIdentifier" = local.cluster_arn
          }
        }
      }]
    })

    resource_discovery = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "AllowRegionalReadActions"
          Effect   = "Allow"
          Resource = "*"
          Action = [
            "ec2:DescribeCapacityReservations",
            "ec2:DescribeImages",
            "ec2:DescribeInstances",
            "ec2:DescribeInstanceStatus",
            "ec2:DescribeInstanceTypeOfferings",
            "ec2:DescribeInstanceTypes",
            "ec2:DescribeLaunchTemplates",
            "ec2:DescribePlacementGroups",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeSpotPriceHistory",
            "ec2:DescribeSubnets"
          ]
          Condition = {
            StringEquals = {
              "aws:RequestedRegion" = data.aws_region.current.region
            }
          }
        },
        {
          Sid      = "AllowSSMReadActions"
          Effect   = "Allow"
          Resource = "arn:${data.aws_partition.current.partition}:ssm:${data.aws_region.current.region}::parameter/aws/service/*"
          Action   = "ssm:GetParameter"
        },
        {
          Sid      = "AllowPricingReadActions"
          Effect   = "Allow"
          Resource = "*"
          Action   = "pricing:GetProducts"
        },
        {
          Sid      = "AllowUnscopedInstanceProfileListAction"
          Effect   = "Allow"
          Resource = "*"
          Action   = "iam:ListInstanceProfiles"
        },
        {
          Sid      = "AllowInstanceProfileReadActions"
          Effect   = "Allow"
          Resource = local.instance_profile_arn
          Action   = "iam:GetInstanceProfile"
        }
      ]
    })
  }
}

resource "aws_iam_policy" "controller" {
  for_each = local.controller_policy_documents

  name        = "${var.name_prefix}-karpenter-${replace(each.key, "_", "-")}"
  description = "Karpenter 1.15 controller ${replace(each.key, "_", " ")} permissions"
  policy      = each.value
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "controller" {
  for_each = aws_iam_policy.controller

  role       = aws_iam_role.controller.name
  policy_arn = each.value.arn
}
