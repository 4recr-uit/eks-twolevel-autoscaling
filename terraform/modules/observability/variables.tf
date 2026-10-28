variable "namespace" {
  description = "Namespace for Prometheus and Grafana"
  type        = string
  default     = "monitoring"
}

variable "chart_version" {
  description = "Pinned kube-prometheus-stack Helm chart version"
  type        = string
  default     = "92.7.0"
}

variable "grafana_admin_secret_name" {
  description = "Existing Kubernetes Secret with admin-user and admin-password keys"
  type        = string
  default     = "grafana-admin"
}
