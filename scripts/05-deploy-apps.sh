#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số." >&2; exit 2; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

# Chart backend nằm ở repo kế bên.
# Kiểm tra monitoring, credentials và CA trước khi deploy.
# Sau khi bật KEDA, dùng thêm worker-keda.yaml khi upgrade ba worker; xem README.
kubectl --context twolevel-dev get crd servicemonitors.monitoring.coreos.com

# Không ghi đè replicas khi worker-scaling đã được cài.
releases=$(helm list --kube-context twolevel-dev --namespace retailstore --short)
if printf "%s\n" "$releases" | grep -Fxq worker-scaling; then
  echo "worker-scaling đã tồn tại; upgrade các chart với worker-keda.yaml theo README." >&2
  exit 1
fi
kubectl --context twolevel-dev -n retailstore get serviceaccount \
  cart-api cart-worker orders-api orders-worker checkout-api checkout-worker
kubectl --context twolevel-dev -n retailstore get configmap rds-ca
kubectl --context twolevel-dev -n retailstore get secret \
  cart-db orders-db checkout-db catalog-db recommendations-db

# Xác nhận MySQL qua Catalog trước các service còn lại.
helm upgrade --install catalog ../retailstore-backend-microservices/src/catalog/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/catalog.yaml --wait --timeout 900s

# Triển khai Recommendations đọc chung dữ liệu Catalog.
helm upgrade --install recommendations ../retailstore-backend-microservices/src/recommendations/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/recommendations.yaml --wait --timeout 900s

# Triển khai Cart API và worker dùng schema cart.
helm upgrade --install cart ../retailstore-backend-microservices/src/cart/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/cart.yaml --wait --timeout 900s

# Triển khai Orders API và worker dùng schema orders.
helm upgrade --install orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/orders.yaml --wait --timeout 900s

# Triển khai Checkout API và worker dùng schema checkout.
helm upgrade --install checkout ../retailstore-backend-microservices/src/checkout/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/checkout.yaml --wait --timeout 900s

# Xác nhận release và trạng thái workload.
helm list --kube-context twolevel-dev --namespace retailstore
kubectl --context twolevel-dev -n retailstore get deployments,pods,services
