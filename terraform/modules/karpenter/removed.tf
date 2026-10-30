removed {
  from = helm_release.karpenter_crd
  lifecycle { destroy = false }
}

removed {
  from = helm_release.karpenter
  lifecycle { destroy = false }
}

removed {
  from = kubectl_manifest.ec2_node_class
  lifecycle { destroy = false }
}

removed {
  from = kubectl_manifest.node_pool
  lifecycle { destroy = false }
}
