#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Dùng một replica ban đầu; chuyển sang KEDA trước khi tạo ScaledObject.
kubectl --context twolevel-dev -n retailstore get deployment carts-worker orders-worker checkout-worker
kubectl --context twolevel-dev get crd clustertriggerauthentications.keda.sh scaledobjects.keda.sh
kubectl --context twolevel-dev -n retailstore get hpa

# Chỉ tạo release nếu chưa có; không vô tình gỡ NodePool khi chạy lại.
releases=$(helm list --all --namespace karpenter --kube-context twolevel-dev --short)
if ! printf "%s\n" "$releases" | grep -Fxq platform-config; then
  helm install platform-config kubernetes/charts/platform-config \
    --namespace karpenter --kube-context twolevel-dev \
    -f kubernetes/environments/dev/platform.yaml --set nodePool.enabled=false --wait --timeout 900s
fi
kubectl --context twolevel-dev get clustertriggerauthentication keda-sqs-pod-identity

# Từ đây về sau, luôn dùng overlay worker-keda.yaml khi upgrade các chart này.
helm upgrade cart ../retailstore-backend-microservices/src/cart/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/cart.yaml -f kubernetes/environments/dev/apps/worker-keda.yaml --wait --timeout 900s
helm upgrade orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/orders.yaml -f kubernetes/environments/dev/apps/worker-keda.yaml --wait --timeout 900s
helm upgrade checkout ../retailstore-backend-microservices/src/checkout/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/checkout.yaml -f kubernetes/environments/dev/apps/worker-keda.yaml --wait --timeout 900s

helm upgrade --install worker-scaling kubernetes/charts/worker-scaling \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/autoscaling.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready \
  scaledobject/carts-worker-sqs scaledobject/orders-worker-sqs scaledobject/checkout-worker-sqs --timeout=900s
