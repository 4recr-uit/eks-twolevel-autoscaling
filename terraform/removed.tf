# Transfer Kubernetes ownership without uninstalling live releases. See docs/MIGRATION.md.
removed {
  from = module.keda
  lifecycle { destroy = false }
}
removed {
  from = module.observability
  lifecycle { destroy = false }
}
