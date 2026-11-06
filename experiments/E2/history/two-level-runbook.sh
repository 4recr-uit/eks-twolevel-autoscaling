#!/usr/bin/env bash
# LỊCH SỬ: Các lệnh bên dưới thuộc thiết kế cũ, KHÔNG dùng cho E mới.
# Đường dẫn và working directory lưu trong file là trước khi di chuyển; không chạy trực tiếp.
# Xem README.md và kiểm tra lại cấu hình, ownership trước mọi thao tác.
# E3: đọc và chạy TỪNG LỆNH trong Git Bash; không chạy toàn bộ file.
exit 0

# 1. CHUẨN BỊ — kiểm tra cluster, tài nguyên E3 và baseline.
# Terminal này cần đang ở thư mục experiments/E3.
kubectl --context twolevel-dev get nodes -o wide
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n karpenter get pods
kubectl --context twolevel-dev -n keda get pods
kubectl --context twolevel-dev -n retailstore get hpa -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
helm status e3-capacity --namespace karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodepool e3-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e3-orders --ignore-not-found
kubectl --context twolevel-dev -n retailstore get deployment e3-warm-capacity --ignore-not-found --show-labels
kubectl --context twolevel-dev -n retailstore get scaledobject e3-orders-sqs --ignore-not-found --show-labels
kubectl --context twolevel-dev -n retailstore get triggerauthentication e3-orders-sqs-auth --ignore-not-found --show-labels
kubectl --context twolevel-dev -n retailstore get hpa e3-orders-keda-hpa --ignore-not-found -o yaml
# Lần đầu: helm status có thể báo release không tồn tại; các tên E3 phải chưa tồn tại.
# Dừng nếu có autoscaler quản lý Orders, queue chưa hết hoặc system node thiếu chỗ.
# Kiểm tra quota EC2, subnet, IAM, AMI alias và chi phí trước khi tạo worker node.
# E3 chỉ chọn c7i-flex.large; nếu không có capacity/AZ phù hợp, kiểm tra trước khi thay values.

# Lưu baseline; không ghi đè. File local có thể chứa dữ liệu nhạy cảm.
umask 077
mkdir -p ../../.generated/e3
test ! -e ../../.generated/e3/orders-original-values.yaml && helm get values orders \
  --namespace retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e3/orders-original-values.yaml
test ! -e ../../.generated/e3/orders-original-replicas.txt && kubectl --context twolevel-dev \
  -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e3/orders-original-replicas.txt
test -s ../../.generated/e3/orders-original-values.yaml
test -s ../../.generated/e3/orders-original-replicas.txt

# 2. NODEPOOL E3 — release mới, không sửa NodePool hoặc auth chung.
# Chỉ install khi tên release/NodePool/NodeClass ở bước 1 chưa tồn tại.
helm template e3-capacity ../../kubernetes/charts/platform-config \
  --namespace karpenter -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e3-capacity ../../kubernetes/charts/platform-config \
  --namespace karpenter --kube-context twolevel-dev \
  -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e3-orders nodepool/e3-orders --timeout=900s

# 3A. WARM — chỉ chạy nhánh này khi muốn chuẩn bị node sẵn.
# 10 pod giữ chỗ có requests như Orders; sẽ tạo EC2 và phát sinh phí.
kubectl --context twolevel-dev -n retailstore apply -f ./warm-capacity.yaml
kubectl --context twolevel-dev -n retailstore rollout status deployment/e3-warm-capacity --timeout=900s
kubectl --context twolevel-dev -n retailstore get pods -l app=e3-warm-capacity -o wide
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e3-orders -o wide

# Sau khi 10 pod Ready, xác nhận Deployment thuộc E3 và xóa pod giữ chỗ.
# Consolidation của NodePool E3 đặt Never, nhưng vẫn phải xác nhận node ổn định.
kubectl --context twolevel-dev -n retailstore get deployment e3-warm-capacity --show-labels
kubectl --context twolevel-dev -n retailstore delete deployment e3-warm-capacity --wait=true
kubectl --context twolevel-dev -n retailstore get pods -l app=e3-warm-capacity
# Nếu còn pod giữ chỗ, chờ chúng chấm dứt trước khi đo.
kubectl --context twolevel-dev -n retailstore wait --for=delete pod -l app=e3-warm-capacity --timeout=300s
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e3-orders -o wide
# Nếu pod đã hết thì bỏ qua wait. Kiểm tra lại requests/allocatable/pod-IP capacity.

# 3B. ELASTIC — bỏ qua 3A. Bắt đầu với NodePool E3 chưa có node dư.
# Khi bật worker min=1 ở bước 4, Karpenter sẽ phải tạo node E3 đầu tiên.
# Chỉ phát workload sau khi worker đầu tiên Ready và xác nhận capacity dư không đủ max=10.
kubectl --context twolevel-dev get nodeclaims -l karpenter.sh/nodepool=e3-orders

# 4. ORDERS + KEDA E3 — áp dụng cho nhánh đã chọn, không dùng scaler chung.
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f ../../.generated/e3/orders-original-values.yaml \
  -f ./autoscaled-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e3-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get pods -o wide
kubectl --context twolevel-dev get nodes,nodeclaims
# Chờ 1 worker Ready, kiểm tra queue rỗng và xác nhận conditions của nhánh.

# 5. WORKLOAD — giữ port-forward trong terminal riêng.
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80

# Terminal khác: chạy profile giống nhau cho 2 nhánh, đổi tên từng lượt.
# Terminal này cần đang ở thư mục experiments/E3.
mkdir -p ./results
k6 run --summary-export ./results/warm-step-1.json ../E1/step.js
k6 run --summary-export ./results/elastic-step-1.json ../E1/step.js
# Chỉ chạy lệnh tương ứng nhánh đã chuẩn bị. Theo dõi queue, pod Pending, node,
# NodeClaim, events, throughput và thời gian. Nếu không có Pending do thiếu
# capacity hoặc không tạo node ở nhánh elastic, điều chỉnh pilot và đo lại.
kubectl --context twolevel-dev -n retailstore get pods -o wide
kubectl --context twolevel-dev get nodeclaims -l karpenter.sh/nodepool=e3-orders
kubectl --context twolevel-dev -n retailstore get events --sort-by=.lastTimestamp

# 6. KHÔI PHỤC — dừng tải, đợi queue hết; kiểm tra tên/owner trước khi xóa.
kubectl --context twolevel-dev -n retailstore get hpa -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
# Dừng nếu autoscaler khác ngoài E3 đang trỏ tới orders-worker.
kubectl --context twolevel-dev -n retailstore delete scaledobject e3-orders-sqs --ignore-not-found --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e3-orders-keda-hpa --ignore-not-found
# Chỉ chạy wait nếu HPA còn tồn tại; chờ KEDA xóa trước khi tiếp tục.
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e3-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e3-orders-sqs-auth --ignore-not-found --wait=true
kubectl --context twolevel-dev -n retailstore delete deployment e3-warm-capacity --ignore-not-found --wait=true

# Trả worker về baseline trước khi gỡ NodePool; giữ system controllers hoạt động.
test -s ../../.generated/e3/orders-original-values.yaml
test -s ../../.generated/e3/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f ../../.generated/e3/orders-original-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e3/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore get pods -o wide

# Chỉ khi đã kiểm tra release E3 và node không chứa workload cần giữ: gỡ release.
# Lệnh này xóa NodePool E3 và có thể chấm dứt EC2; không gỡ Karpenter controller.
helm status e3-capacity --namespace karpenter --kube-context twolevel-dev
helm uninstall e3-capacity --namespace karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodeclaims -l karpenter.sh/nodepool=e3-orders
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e3-orders
# Kiểm tra NodeClaim/node/EC2 E3 đã được thu hồi trước khi tắt controller.
# Để đo nhánh còn lại, giữ file baseline và bắt đầu lại từ bước 2.
# Sau khi kết thúc mọi nhánh và xác nhận khôi phục thành công, xóa file lưu tạm.
rm -f -- ../../.generated/e3/orders-original-values.yaml ../../.generated/e3/orders-original-replicas.txt
