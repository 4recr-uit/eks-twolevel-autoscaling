# Preserve state addresses if Karpenter/KEDA were applied before the staged
# deployment switch was introduced.
moved {
  from = module.karpenter
  to   = module.karpenter[0]
}

moved {
  from = module.keda
  to   = module.keda[0]
}
