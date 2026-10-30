#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Chạy từ thư mục gốc repo hạ tầng, dùng cấu hình dev.
# Chuẩn bị image, DB users/schema và các Secret được tham chiếu trong YAML trước.
# Nếu repo backend nằm chỗ khác, sửa đường dẫn chart ở từng lệnh bên dưới.
# cart
helm upgrade --install cart ../retailstore-backend-microservices/src/cart/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/cart.yaml --wait --timeout 900s

# orders
helm upgrade --install orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/orders.yaml --wait --timeout 900s

# checkout
helm upgrade --install checkout ../retailstore-backend-microservices/src/checkout/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/checkout.yaml --wait --timeout 900s

# catalog
helm upgrade --install catalog ../retailstore-backend-microservices/src/catalog/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/catalog.yaml --wait --timeout 900s

# recommendations
helm upgrade --install recommendations ../retailstore-backend-microservices/src/recommendations/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/recommendations.yaml --wait --timeout 900s
