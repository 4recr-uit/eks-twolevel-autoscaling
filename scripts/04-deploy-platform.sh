#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Kiểm tra monitoring và render cấu hình trước khi cài platform.
kubectl --context twolevel-dev wait --for=condition=Established crd/servicemonitors.monitoring.coreos.com --timeout=900s
helm template platform-config kubernetes/charts/platform-config -f kubernetes/environments/dev/platform.yaml > /dev/null

# Cài đặt Metrics Server để cung cấp CPU/memory metrics cho HPA và kubectl top.
helm upgrade --install metrics-server metrics-server --repo https://kubernetes-sigs.github.io/metrics-server/ \
  --version 3.14.0 --namespace kube-system --kube-context twolevel-dev \
  -f kubernetes/platform/metrics-server/values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=120s

# Cài Karpenter CRDs trước controller.
helm upgrade --install karpenter-crd oci://public.ecr.aws/karpenter/karpenter-crd \
  --version 1.15.0 --namespace karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Established crd/ec2nodeclasses.karpenter.k8s.aws crd/nodepools.karpenter.sh --timeout=900s

helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
  --version 1.15.0 --namespace karpenter --kube-context twolevel-dev --skip-crds \
  -f kubernetes/platform/karpenter/values.yaml \
  -f kubernetes/environments/dev/karpenter.yaml --wait --timeout 900s

# Cài KEDA với ServiceAccount đã được liên kết Pod Identity.
helm upgrade --install keda keda --repo https://kedacore.github.io/charts \
  --version 2.21.0 --namespace keda --kube-context twolevel-dev \
  -f kubernetes/platform/keda/values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Established crd/scaledobjects.keda.sh crd/clustertriggerauthentications.keda.sh --timeout=900s

# Chỉ cài controller. Tạo auth ở bước KEDA và NodePool ở bước riêng.
