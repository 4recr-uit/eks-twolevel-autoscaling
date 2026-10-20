# Optional experiment stack. Keep dashboards private and use port-forwarding;
# no public load balancer or persistent volume is provisioned by default.
resource "helm_release" "monitoring" {
  name             = "monitoring"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = var.chart_version
  namespace        = var.namespace
  create_namespace = true

  atomic  = true
  wait    = true
  timeout = 900

  values = [yamlencode({
    defaultRules = { create = false }
    alertmanager = { enabled = false }
    grafana = {
      admin = {
        existingSecret = var.grafana_admin_secret_name
        userKey        = "admin-user"
        passwordKey    = "admin-password"
      }
      service = { type = "ClusterIP" }
    }
    prometheus = {
      prometheusSpec = {
        retention                               = "24h"
        serviceMonitorSelectorNilUsesHelmValues = false
        podMonitorSelectorNilUsesHelmValues     = false
        resources = {
          requests = { cpu = "200m", memory = "512Mi" }
          limits   = { cpu = "1", memory = "1Gi" }
        }
      }
    }
  })]
}
