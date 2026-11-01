#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Bật NodePool trong release đã tạo ở bước KEDA.
helm status platform-config --namespace karpenter --kube-context twolevel-dev
helm upgrade platform-config kubernetes/charts/platform-config \
  --namespace karpenter --kube-context twolevel-dev \
  -f kubernetes/environments/dev/platform.yaml --set nodePool.enabled=true --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/default nodepool/default --timeout=900s
