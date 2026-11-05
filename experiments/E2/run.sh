#!/usr/bin/env bash
# E2: đọc và chạy TỪNG LỆNH trong Git Bash; không chạy toàn bộ file.
exit 0

# 1. CHUẨN BỊ — dừng nếu đã có HPA/ScaledObject quản lý orders-worker.
# Terminal này cần đang ở thư mục experiments/E2.
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev get nodes -o wide
kubectl --context twolevel-dev -n retailstore get hpa -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n keda get pods
kubectl --context twolevel-dev -n retailstore get scaledobject e2-orders-sqs --ignore-not-found --show-labels
kubectl --context twolevel-dev -n retailstore get triggerauthentication e2-orders-sqs-auth --ignore-not-found --show-labels
kubectl --context twolevel-dev -n retailstore get hpa e2-orders-keda-hpa --ignore-not-found -o yaml
# Trước lần đầu: tên E2 phải chưa tồn tại; queue visible/in-flight/delayed về 0,
# kiểm tra DLQ, node capacity, Metrics/Prometheus và giữ node ổn định.

# Lưu baseline, không ghi đè. Dừng nếu một lệnh test hoặc lưu thất bại.
umask 077
mkdir -p ../../.generated/e2
test ! -e ../../.generated/e2/orders-original-values.yaml && helm get values orders \
  --namespace retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e2/orders-original-values.yaml
test ! -e ../../.generated/e2/orders-original-replicas.txt && kubectl --context twolevel-dev \
  -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e2/orders-original-replicas.txt
test -s ../../.generated/e2/orders-original-values.yaml
test -s ../../.generated/e2/orders-original-replicas.txt

# 2. BẬT KEDA E2 — min 0; không dùng chung ScaledObject của E1/release khác.
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f ../../.generated/e2/orders-original-values.yaml \
  -f ./autoscaled-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e2-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects,deployments,pods
# Chờ orders-worker về 0 và queue rỗng trước first job; Ready không đảm bảo không lỗi IAM sau đó.

# 3. TẠO TẢI — terminal riêng giữ port-forward; Ctrl+C khi xong.
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80

# Terminal khác: gửi MỘT job, ghi enqueuedAt/jobId và thời điểm phản hồi.
# Đối chiếu đúng jobId với log worker; light ghi dữ liệu thử vào DB.
# Terminal này cần đang ở thư mục experiments/E2.
curl -i -X POST http://localhost:8082/jobs -H 'Content-Type: application/json' \
  -d '{"workUnits":100,"dbMode":"light","batchSize":1,"customerId":"test-e2"}'
kubectl --context twolevel-dev -n retailstore get pods -o wide
# Chỉ xem log sau khi worker đã được tạo; nếu chưa có pod, chờ và kiểm tra lại.
kubectl --context twolevel-dev -n retailstore logs deployment/orders-worker --tail=100

# Sau first job, tạo tải step; giữ nguyên profile giữa các lượt và đổi tên kết quả.
mkdir -p ./results
k6 run -e PROFILE=step --summary-export ./results/e2-step-1.json ../E1/workload.js
# Ngừng gửi, theo dõi queue/desired/ready và chờ worker về 0; ghi mốc, retry/DLQ.
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects,pods

# 4. KHÔI PHỤC — dừng tải, chờ queue hết; xác nhận label owner=e2 trước khi xóa.
# Dừng nếu có autoscaler ngoài E2 đang trỏ tới orders-worker.
kubectl --context twolevel-dev -n retailstore get hpa -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore delete scaledobject e2-orders-sqs --ignore-not-found --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e2-orders-keda-hpa --ignore-not-found
# Nếu HPA còn tồn tại thì chạy wait; nếu không tồn tại thì bỏ qua.
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e2-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e2-orders-sqs-auth --ignore-not-found --wait=true
test -s ../../.generated/e2/orders-original-values.yaml
test -s ../../.generated/e2/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f ../../.generated/e2/orders-original-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e2/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
# Chỉ xóa bản lưu sau khi đã xác nhận khôi phục thành công.
rm -f -- ../../.generated/e2/orders-original-values.yaml ../../.generated/e2/orders-original-replicas.txt
