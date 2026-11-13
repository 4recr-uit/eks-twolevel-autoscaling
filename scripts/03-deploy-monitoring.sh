#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số." >&2; exit 2; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

# 1. Kiểm tra Secret chứa thông tin đăng nhập Grafana trước khi triển khai.
kubectl --context twolevel-dev -n monitoring get secret grafana-admin

# 2. Cài hoặc cập nhật Prometheus Operator, Prometheus và Grafana bằng Helm.
helm upgrade --install monitoring kube-prometheus-stack \
  --repo https://prometheus-community.github.io/helm-charts \
  --version 92.7.0 --namespace monitoring --kube-context twolevel-dev \
  -f kubernetes/platform/monitoring/values.yaml --wait --timeout 900s

# 3. Chờ ServiceMonitor CRD sẵn sàng cho các bước deploy tiếp theo và xem Pod.
kubectl --context twolevel-dev wait --for=condition=Established crd/servicemonitors.monitoring.coreos.com --timeout=900s
kubectl --context twolevel-dev -n monitoring get pods

# 4. Cập nhật riêng dashboard từ JSON vào ConfigMap; gắn nhãn để Grafana nhận diện.
# Khi chạy riêng hai lệnh dưới đây, trước tiên chuyển từ scripts về thư mục gốc repo.
kubectl --context twolevel-dev -n monitoring create configmap autoscaling-dashboard \
  --from-file=observability/dashboards/autoscaling-overview.json --dry-run=client -o yaml | \
  kubectl --context twolevel-dev apply -f -
kubectl --context twolevel-dev -n monitoring label configmap autoscaling-dashboard grafana_dashboard=1 --overwrite
