#!/usr/bin/env bash
# E1: chạy TỪNG LỆNH trong Git Bash theo thứ tự; không chạy toàn bộ file.
# Dòng này ngăn thao tác hàng loạt nếu vô tình chạy: bash experiments/E1/run.sh
exit 0

# 1. CHUẨN BỊ — chạy một lần từ máy local.
cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling

# Xem worker, node và metric CPU; xác nhận đủ capacity cho 10 worker.
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev get nodes -o wide
kubectl --context twolevel-dev top nodes
kubectl --context twolevel-dev -n retailstore top pods

# Xem cột TARGET. Dừng nếu HPA hoặc ScaledObject khác trỏ đến orders-worker.
kubectl --context twolevel-dev -n retailstore get hpa \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name

# Kiểm tra các tên E1 chưa bị tài nguyên khác chiếm dụng.
kubectl --context twolevel-dev -n retailstore get hpa e1-orders-cpu --ignore-not-found --show-labels
kubectl --context twolevel-dev -n retailstore get scaledobject e1-orders-sqs --ignore-not-found --show-labels
kubectl --context twolevel-dev -n retailstore get triggerauthentication e1-orders-sqs-auth --ignore-not-found --show-labels
kubectl --context twolevel-dev -n retailstore get hpa e1-orders-keda-hpa --ignore-not-found -o yaml
# Nếu đã tồn tại: chỉ tiếp tục khi label experiments.retailstore.dev/owner=e1;
# riêng e1-orders-keda-hpa phải có ownerReference là ScaledObject e1-orders-sqs.
# Trước lượt đầu E1, không được có autoscaler nào trỏ đến orders-worker.

# Lưu Helm user values và số replica ban đầu; không ghi đè bản lưu đang có.
# .generated/ đã gitignore; values có thể chứa dữ liệu nhạy cảm, không chia sẻ.
umask 077
mkdir -p .generated/e1
test ! -e .generated/e1/orders-original-values.yaml && helm get values orders \
  --namespace retailstore --kube-context twolevel-dev -o yaml > .generated/e1/orders-original-values.yaml
test ! -e .generated/e1/orders-original-replicas.txt && kubectl --context twolevel-dev \
  -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > .generated/e1/orders-original-replicas.txt

# Xác nhận hai file khác rỗng; nếu lệnh thất bại, dừng và kiểm tra.
test -s .generated/e1/orders-original-values.yaml
test -s .generated/e1/orders-original-replicas.txt

# 2. FIXED — 2 worker; chạy sau khi kiểm tra và lưu baseline.
helm upgrade orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f .generated/e1/orders-original-values.yaml \
  -f experiments/E1/fixed-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore get deployment orders-worker

# Mở terminal riêng để giữ port-forward trong lúc chạy k6.
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80

# Trong terminal Git Bash khác, chạy từng profile k6 từ repo hạ tầng.
# Trước mỗi lượt, đợi queue hoàn tất; đổi tên file để không ghi đè kết quả.
cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling
mkdir -p experiments/E1/results
k6 run -e PROFILE=steady --summary-export experiments/E1/results/fixed-steady-1.json experiments/E1/workload.js
k6 run -e PROFILE=step --summary-export experiments/E1/results/fixed-step-1.json experiments/E1/workload.js
k6 run -e PROFILE=burst --summary-export experiments/E1/results/fixed-burst-1.json experiments/E1/workload.js

# 3. CPU-HPA — chỉ chuyển khi queue hết tải, không có ScaledObject cho Orders.
kubectl --context twolevel-dev -n retailstore get hpa \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
# Chỉ tiếp tục khi không còn HPA/ScaledObject nào trỏ tới orders-worker.
helm upgrade orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f .generated/e1/orders-original-values.yaml \
  -f experiments/E1/autoscaled-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f experiments/E1/hpa.yaml
kubectl --context twolevel-dev -n retailstore get hpa e1-orders-cpu

# Chạy từng profile, chờ queue hoàn tất giữa các lượt.
k6 run -e PROFILE=steady --summary-export experiments/E1/results/hpa-steady-1.json experiments/E1/workload.js
k6 run -e PROFILE=step --summary-export experiments/E1/results/hpa-step-1.json experiments/E1/workload.js
k6 run -e PROFILE=burst --summary-export experiments/E1/results/hpa-burst-1.json experiments/E1/workload.js

# 4. KEDA — chỉ chuyển khi queue hết tải và HPA E1 thuộc thí nghiệm.
kubectl --context twolevel-dev -n retailstore delete hpa e1-orders-cpu --wait=true
kubectl --context twolevel-dev -n retailstore get hpa \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
# Chỉ tiếp tục khi không còn HPA/ScaledObject nào khác trỏ tới orders-worker.
helm upgrade orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f .generated/e1/orders-original-values.yaml \
  -f experiments/E1/autoscaled-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f experiments/E1/keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready \
  scaledobject/e1-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects

# Chạy từng profile, chờ queue hoàn tất giữa các lượt.
k6 run -e PROFILE=steady --summary-export experiments/E1/results/keda-steady-1.json experiments/E1/workload.js
k6 run -e PROFILE=step --summary-export experiments/E1/results/keda-step-1.json experiments/E1/workload.js
k6 run -e PROFILE=burst --summary-export experiments/E1/results/keda-burst-1.json experiments/E1/workload.js

# 5. KHÔI PHỤC — dừng k6, chờ queue hết tải; xác nhận quyền sở hữu E1 trước.
# Chỉ xóa tài nguyên sau khi xác nhận tên/label/owner ở phần chuẩn bị.
kubectl --context twolevel-dev -n retailstore get hpa \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
kubectl --context twolevel-dev -n retailstore get scaledobjects \
  -o custom-columns=NAME:.metadata.name,TARGET:.spec.scaleTargetRef.name
# Dừng nếu có autoscaler ngoài E1 trỏ đến orders-worker.
kubectl --context twolevel-dev -n retailstore delete hpa e1-orders-cpu --ignore-not-found --wait=true
kubectl --context twolevel-dev -n retailstore delete scaledobject e1-orders-sqs --ignore-not-found --wait=true

# Nếu HPA e1-orders-keda-hpa còn tồn tại, chạy lệnh wait; nếu không, bỏ qua.
kubectl --context twolevel-dev -n retailstore get hpa e1-orders-keda-hpa --ignore-not-found
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e1-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e1-orders-sqs-auth --ignore-not-found --wait=true

# Khôi phục Helm user values và số replica đã lưu; dùng đúng chart như trước E1.
test -s .generated/e1/orders-original-values.yaml
test -s .generated/e1/orders-original-replicas.txt
helm upgrade orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f .generated/e1/orders-original-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker \
  --replicas="$(cat .generated/e1/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects

# Chỉ sau khi xác nhận khôi phục thành công, xóa hai file lưu tạm nhạy cảm.
rm -f -- .generated/e1/orders-original-values.yaml .generated/e1/orders-original-replicas.txt

