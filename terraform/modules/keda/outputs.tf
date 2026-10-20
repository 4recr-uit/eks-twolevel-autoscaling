output "release_name" {
  description = "Name of the installed KEDA Helm release"
  value       = helm_release.keda.name
}

output "operator_service_account_name" {
  description = "ServiceAccount associated with the KEDA Pod Identity IAM role"
  value       = "keda-operator"
}

output "cluster_trigger_authentication_name" {
  description = "ClusterTriggerAuthentication shared by the SQS ScaledObjects"
  value       = local.trigger_auth_name
}

output "scaled_object_names" {
  description = "ScaledObject names by logical SQS queue name; empty until enabled"
  value       = { for queue_name, object in kubectl_manifest.scaled_object : queue_name => "${var.worker_deployments[queue_name]}-sqs" }
}
