#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Chạy từ thư mục gốc repo hạ tầng, dùng cấu hình dev.
# Kiểm tra ba worker đã được triển khai. Không bật thêm HPA/ScaledObject từ chart backend.
kubectl --context twolevel-dev -n retailstore get deployment carts-worker orders-worker checkout-worker
kubectl --context twolevel-dev get clustertriggerauthentication keda-sqs-pod-identity
kubectl --context twolevel-dev -n retailstore get hpa

helm upgrade --install worker-scaling kubernetes/charts/worker-scaling \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/autoscaling.yaml --wait --timeout 900s

kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready \
  scaledobject/carts-worker-sqs scaledobject/orders-worker-sqs scaledobject/checkout-worker-sqs --timeout=900s
