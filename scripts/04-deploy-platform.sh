#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Chạy từ thư mục gốc repo hạ tầng, dùng cấu hình dev.
helm template platform-config kubernetes/charts/platform-config -f kubernetes/environments/dev/platform.yaml > /dev/null

# Cài monitoring trước: các values mặc định bật ServiceMonitor.
# Karpenter: cài CRDs trước controller và chính sách tạo node.
helm upgrade --install karpenter-crd oci://public.ecr.aws/karpenter/karpenter-crd \
  --version 1.15.0 --namespace karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Established crd/ec2nodeclasses.karpenter.k8s.aws crd/nodepools.karpenter.sh --timeout=900s

helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
  --version 1.15.0 --namespace karpenter --kube-context twolevel-dev --skip-crds \
  -f kubernetes/platform/karpenter/values.yaml \
  -f kubernetes/environments/dev/karpenter.yaml --wait --timeout 900s

# KEDA operator dùng ServiceAccount keda-operator đã được AWS Pod Identity liên kết.
helm upgrade --install keda keda --repo https://kedacore.github.io/charts \
  --version 2.21.0 --namespace keda --kube-context twolevel-dev \
  -f kubernetes/platform/keda/values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Established crd/scaledobjects.keda.sh crd/clustertriggerauthentications.keda.sh --timeout=900s

# NodePool, EC2NodeClass, ClusterTriggerAuthentication và Catalog ServiceMonitor.
helm upgrade --install platform-config kubernetes/charts/platform-config \
  --namespace karpenter --kube-context twolevel-dev \
  -f kubernetes/environments/dev/platform.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/default nodepool/default --timeout=900s
