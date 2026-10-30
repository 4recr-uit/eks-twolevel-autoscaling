#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Chạy từ thư mục gốc repo hạ tầng, dùng cấu hình dev.
# Chỉ kiểm tra trạng thái; không sinh cấu hình hoặc gửi tải thử.
kubectl --context twolevel-dev -n karpenter rollout status deployment/karpenter --timeout=900s
kubectl --context twolevel-dev -n keda rollout status deployment/keda-operator --timeout=900s
kubectl --context twolevel-dev -n keda rollout status deployment/keda-operator-metrics-apiserver --timeout=900s
kubectl --context twolevel-dev -n keda rollout status deployment/keda-admission-webhooks --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/carts-api --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/carts-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-api --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/checkout-api --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/checkout-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/catalog --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/recommendations --timeout=900s
kubectl --context twolevel-dev -n monitoring rollout status deployment/monitoring-grafana --timeout=900s
kubectl --context twolevel-dev -n monitoring rollout status deployment/monitoring-kube-prometheus-operator --timeout=900s
kubectl --context twolevel-dev -n monitoring rollout status deployment/monitoring-kube-state-metrics --timeout=900s
kubectl --context twolevel-dev -n monitoring rollout status statefulset/prometheus-monitoring-kube-prometheus-prometheus --timeout=900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/default nodepool/default --timeout=900s
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/carts-worker-sqs scaledobject/orders-worker-sqs scaledobject/checkout-worker-sqs --timeout=900s
kubectl --context twolevel-dev -n retailstore get pods,scaledobjects,hpa
kubectl --context twolevel-dev get nodes,nodeclaims
kubectl --context twolevel-dev -n monitoring get pods,svc
# Sau bước này cần thử API -> SQS -> worker -> DB và quan sát scale-out/scale-in.
