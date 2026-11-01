#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số; xem scripts/README.md." >&2; exit 2; }

# Xác thực AWS và cấu hình context EKS dev.
aws sts get-caller-identity
aws eks update-kubeconfig --region us-east-1 --name twolevel-autoscaling-dev --alias twolevel-dev
kubectl config use-context twolevel-dev

# Kiểm tra trạng thái node và chờ node sẵn sàng.
kubectl --context twolevel-dev get nodes
kubectl --context twolevel-dev wait --for=condition=Ready nodes -l role=system --timeout=900s

# Tạo namespaces và service accounts.
kubectl --context twolevel-dev apply -k kubernetes/namespaces
kubectl --context twolevel-dev apply -k kubernetes/apps

# Xác nhận tài nguyên nền đã sẵn sàng.
kubectl --context twolevel-dev get namespaces
kubectl --context twolevel-dev -n retailstore get serviceaccounts
