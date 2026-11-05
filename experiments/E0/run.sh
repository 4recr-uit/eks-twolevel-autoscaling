#!/usr/bin/env bash
# E0: chạy TỪNG NHÓM LỆNH trong Git Bash; không chạy toàn bộ file.
exit 0

# Terminal này cần đang ở thư mục experiments/E0.

# Chuẩn bị: dừng nếu HPA/ScaledObject nào trỏ đến orders-worker.
kubectl --context twolevel-dev -n retailstore get hpa \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name

# Lưu user values và replicas trước khi thay đổi. Không ghi đè bản lưu cũ.
umask 077
mkdir -p ../../.generated/e0
test ! -e ../../.generated/e0/orders-original-values.yaml && helm get values orders \
  --namespace retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e0/orders-original-values.yaml
test ! -e ../../.generated/e0/orders-original-replicas.txt && kubectl --context twolevel-dev \
  -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e0/orders-original-replicas.txt
test -s ../../.generated/e0/orders-original-values.yaml
test -s ../../.generated/e0/orders-original-replicas.txt

# Cố định 1 worker. Cần giữ cùng chart, image, request, concurrency, queue và DB.
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f ../../.generated/e0/orders-original-values.yaml \
  -f ./fixed-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s

# Tạo hồ sơ, thu, chạy workload và đợi drain theo README E0.

# Khôi phục sau khi dừng workload và queue drain; trước tiên xác nhận không có autoscaler khác.
kubectl --context twolevel-dev -n retailstore get hpa \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
test -s ../../.generated/e0/orders-original-values.yaml
test -s ../../.generated/e0/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f ../../.generated/e0/orders-original-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker \
  --replicas="$(cat ../../.generated/e0/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore get deployment orders-worker

# Chỉ sau khi xác nhận khôi phục thành công, xóa hai bản lưu nhạy cảm.
rm -f -- ../../.generated/e0/orders-original-values.yaml ../../.generated/e0/orders-original-replicas.txt
