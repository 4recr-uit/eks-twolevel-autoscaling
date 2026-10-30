#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Chạy từ thư mục gốc repo hạ tầng, dùng cấu hình dev.
# Kết nối kubectl với cluster và tạo namespace/ServiceAccount.
aws sts get-caller-identity
aws eks update-kubeconfig --region us-east-1 --name twolevel-autoscaling-dev --alias twolevel-dev
kubectl config use-context twolevel-dev
kubectl get nodes
kubectl wait --for=condition=Ready nodes -l role=system --timeout=900s
kubectl apply -k kubernetes/namespaces
kubectl apply -k kubernetes/apps

# Kiểm tra namespace/ServiceAccount đã tồn tại.
kubectl get namespaces
kubectl -n retailstore get serviceaccounts