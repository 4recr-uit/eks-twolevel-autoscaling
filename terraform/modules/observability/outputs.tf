output "release_name" {
  description = "Name of the monitoring Helm release"
  value       = helm_release.monitoring.name
}

output "grafana_service_name" {
  description = "Internal Grafana service for kubectl port-forward"
  value       = "${helm_release.monitoring.name}-grafana"
}
