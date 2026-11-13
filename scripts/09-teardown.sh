#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số." >&2; exit 2; }

# Dùng cấu hình dev.
# Chỉ chạy khi muốn gỡ ứng dụng; dừng tải/producer và xử lý hoặc bảo toàn message trước.
# Giữ lại KEDA, monitoring, CRDs, namespace, Secret/PVC và AWS resources.
helm uninstall worker-scaling --namespace retailstore --kube-context twolevel-dev --ignore-not-found --wait --timeout 900s
helm uninstall cart --namespace retailstore --kube-context twolevel-dev --ignore-not-found --wait --timeout 900s
helm uninstall orders --namespace retailstore --kube-context twolevel-dev --ignore-not-found --wait --timeout 900s
helm uninstall checkout --namespace retailstore --kube-context twolevel-dev --ignore-not-found --wait --timeout 900s
helm uninstall catalog --namespace retailstore --kube-context twolevel-dev --ignore-not-found --wait --timeout 900s
helm uninstall recommendations --namespace retailstore --kube-context twolevel-dev --ignore-not-found --wait --timeout 900s

# Giữ controller hoạt động cho đến khi node/EC2 được xử lý xong.
kubectl --context twolevel-dev delete nodepool default --ignore-not-found --cascade=foreground --wait=true --timeout=900s
kubectl --context twolevel-dev delete nodeclaim -l karpenter.sh/nodepool=default --ignore-not-found --wait=true --timeout=900s
# Nếu còn NodeClaim ở pool khác hoặc đang kẹt, dừng trước khi gỡ controller.
remaining_nodeclaims=$(kubectl --context twolevel-dev get nodeclaims -o name)
if [[ -n "$remaining_nodeclaims" ]]; then
  echo "Còn NodeClaim; giữ lại Karpenter controller. Kiểm tra: kubectl --context twolevel-dev get nodeclaims" >&2
  exit 1
fi
helm uninstall platform-config --namespace karpenter --kube-context twolevel-dev --ignore-not-found --wait --timeout 900s
helm uninstall karpenter --namespace karpenter --kube-context twolevel-dev --ignore-not-found --wait --timeout 900s
# Terraform destroy là bước riêng, phải review tài nguyên/dữ liệu cần giữ trước.
