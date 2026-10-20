locals {
  trigger_auth_name = "keda-sqs-pod-identity"
}

# Chart creates the KEDA CRDs, operator, metrics API server, webhook, and
# keda-operator ServiceAccount used by the existing EKS Pod Identity association.
resource "helm_release" "keda" {
  name             = "keda"
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  version          = var.keda_version
  namespace        = var.keda_namespace
  create_namespace = true

  atomic  = true
  wait    = true
  timeout = 600

  values = [yamlencode({
    serviceAccount = {
      operator = {
        create = true
        name   = "keda-operator"
      }
    }
  })]
}

# The operator assumes its Pod Identity IAM role and polls only the three main
# queues. Cluster scope lets all three workload ScaledObjects reuse this auth.
resource "kubectl_manifest" "sqs_auth" {
  yaml_body = yamlencode({
    apiVersion = "keda.sh/v1alpha1"
    kind       = "ClusterTriggerAuthentication"
    metadata = {
      name = local.trigger_auth_name
    }
    spec = {
      podIdentity = {
        provider      = "aws"
        identityOwner = "keda"
      }
    }
  })

  validate_schema = false
  depends_on      = [helm_release.keda]
}

# App Deployments are provisioned separately. Enable these only after the
# retailstore namespace and matching worker Deployments have been applied.
resource "kubectl_manifest" "scaled_object" {
  for_each = var.enable_scaled_objects ? var.worker_deployments : {}

  yaml_body = yamlencode({
    apiVersion = "keda.sh/v1alpha1"
    kind       = "ScaledObject"
    metadata = {
      name      = "${each.value}-sqs"
      namespace = var.app_namespace
    }
    spec = {
      scaleTargetRef = {
        name = each.value
      }
      pollingInterval = var.polling_interval
      cooldownPeriod  = var.cooldown_period
      minReplicaCount = var.min_replica_count
      maxReplicaCount = var.max_replica_count
      triggers = [{
        type = "aws-sqs-queue"
        metadata = {
          queueURL        = var.queue_urls[each.key]
          awsRegion       = var.aws_region
          queueLength     = tostring(var.queue_length)
          scaleOnInFlight = "true"
        }
        authenticationRef = {
          name = local.trigger_auth_name
          kind = "ClusterTriggerAuthentication"
        }
      }]
    }
  })

  validate_schema = false
  depends_on      = [kubectl_manifest.sqs_auth]

  lifecycle {
    precondition {
      condition     = contains(keys(var.queue_urls), each.key)
      error_message = "Each worker_deployments key must match a key in queue_urls."
    }
  }
}
