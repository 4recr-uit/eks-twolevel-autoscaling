#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Chạy từ thư mục gốc repo hạ tầng, dùng cấu hình dev.
# Chuẩn bị Secret grafana-admin (admin-user, admin-password) trước khi chạy.
helm upgrade --install monitoring kube-prometheus-stack \
  --repo https://prometheus-community.github.io/helm-charts \
  --version 92.7.0 --namespace monitoring --kube-context twolevel-dev \
  -f kubernetes/platform/monitoring/values.yaml --wait --timeout 900s

kubectl --context twolevel-dev wait --for=condition=Established crd/servicemonitors.monitoring.coreos.com --timeout=900s
kubectl --context twolevel-dev -n monitoring create configmap autoscaling-dashboard \
  --from-file=observability/dashboards/autoscaling-overview.json --dry-run=client -o yaml | \
  kubectl --context twolevel-dev apply -f -
kubectl --context twolevel-dev -n monitoring label configmap autoscaling-dashboard grafana_dashboard=1 --overwrite
