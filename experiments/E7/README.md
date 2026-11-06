# E7 — Queue Target Sensitivity

E7 khảo sát queueLength của KEDA với ba cấu hình q-low=5, q-medium=10, q-high=20. Đây là các mức pilot cần xem lại theo μ, không phải kết quả đã đo. Chỉ đổi queue target; giữ cùng workload, worker, node capacity, max replica và cửa sổ. Chạy một profile đại diện, lặp từng mức khi điều kiện cho phép.

Tất cả lệnh chạy từ `experiments/E7`; workload, manifests, init, collector và report nằm ngay đây. KEDA/Karpenter/API/monitoring phải có node hệ thống độc lập. Giá trị là pilot, **chưa xác minh trên cluster**. Kiểm tra quota/IAM/subnet và chi phí trước khi chạy. KEDA min 1/max 10, polling 30s, cooldown 300s; NodePool `e7-orders` On-Demand, worker request 500m/256Mi. Thay đổi request so với E0 có thể ảnh hưởng throughput, phải pilot lại. Step 5→10→15→20→15→10→5/s, mỗi bậc 1 phút; Burst 5→40→5/s với đỉnh 30 giây; Steady 5/s 2 phút.

## 1. Điều kiện và baseline

Kiểm tra context, node, các HPA/ScaledObject trỏ `orders-worker`, queue/DLQ, producer khác, requests/limits, region và monitoring. Dừng nếu controller khác đang quản lý worker hoặc các tên `e7-orders*`/release `e7-capacity` đã thuộc tài nguyên khác. Không purge queue. Lưu baseline không ghi đè:

```bash
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects
kubectl --context twolevel-dev get nodes,nodeclaims -o wide
kubectl --context twolevel-dev get nodepool e7-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e7-orders --ignore-not-found
helm status e7-capacity -n karpenter --kube-context twolevel-dev
umask 077
mkdir -p ../../.generated/e7
test ! -e ../../.generated/e7/orders-original-values.yaml && helm get values orders -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e7/orders-original-values.yaml
test ! -e ../../.generated/e7/orders-original-replicas.txt && kubectl --context twolevel-dev -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e7/orders-original-replicas.txt
test -s ../../.generated/e7/orders-original-values.yaml && test -s ../../.generated/e7/orders-original-replicas.txt
```

Nếu release chưa tồn tại `helm status` có thể báo lỗi. Dừng nếu baseline không lưu được. Xác nhận KEDA và Karpenter hoạt động, target Prometheus UP, quyền AWS và queue mà worker/KEDA dùng đúng.

## 2. Áp dụng cấu hình

Chỉ sau khi kiểm tra tài nguyên và release chưa tồn tại:

```bash
helm template e7-capacity ../../kubernetes/charts/platform-config -n karpenter -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e7-capacity ../../kubernetes/charts/platform-config -n karpenter --kube-context twolevel-dev -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e7-orders nodepool/e7-orders --timeout=900s
```

Sau khi NodePool sẵn sàng, apply `warm-capacity.yaml`, chờ rollout và xóa Deployment giữ chỗ; sau đó kiểm tra số node, CPU/memory/Pod-IP trống đủ cho max worker và giữ nguyên điều kiện cho cả ba mức. Xem YAML và quota: thao tác này tạo EC2 và tính phí. NodePool `consolidateAfter: Never` giữ node.

```bash
kubectl --context twolevel-dev -n retailstore apply -f ./warm-capacity.yaml
kubectl --context twolevel-dev -n retailstore rollout status deployment/e7-warm-capacity --timeout=900s
kubectl --context twolevel-dev -n retailstore get deployment e7-warm-capacity --show-labels
kubectl --context twolevel-dev -n retailstore delete deployment e7-warm-capacity --wait=true
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e7/orders-original-values.yaml -f ./autoscaled-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda-medium.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e7-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects,deployments,pods -o wide
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e7-orders -o wide
```

Áp dụng đúng một trong `keda-low.yaml`, `keda-medium.yaml`, `keda-high.yaml`; chúng cùng tên ScaledObject và chỉ khác queueLength. Khi đổi mức, chờ queue drain và KEDA về một worker, rồi apply file tương ứng và kiểm tra ScaledObject/HPA; collector kiểm tra queueLength khớp variant. Chuẩn bị đủ node capacity trong cả ba mức để việc cấp node không trở thành biến độc lập, và ghi mọi trường hợp Pending/node mới. `--server-side=false` yêu cầu Helm 4; dừng nếu rollout/conflict thất bại, không tự dùng `--force-conflicts`. Chờ đúng một desired/Ready worker và queue rỗng trước mỗi lượt.

## 3. Thu một lượt

Ví dụ q-medium-burst-r01. **Terminal 1:**

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E7/E7-q-medium-burst-r01
bash ./run.sh init --variant q-medium --profile burst --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Chờ `ĐANG THU` rồi tối thiểu 75 giây baseline. **Terminal 2:**

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E7/E7-q-medium-burst-r01
bash ./run.sh load burst "$RUN_DIR"
```

Sau khi workload kết thúc, chờ ít nhất 60 giây và tiếp tục đến khi queue/DLQ được đối chiếu và drain theo nhiều mẫu. Nhấn Ctrl+C một lần tại collector, đợi xuất metric; đóng từng port-forward bằng PID của terminal đó. Đổi `RUN_DIR`, variant và attempt cho mỗi lượt; các file không ghi đè.

## 4. Báo cáo

```bash
bash ./run.sh report --run-dir "$RUN_DIR"
```

Mặc định report dùng 60 giây idle trước và 60 giây sau workload cho Node-minutes, tính từ node Kubernetes được lấy mẫu; không thay thế EC2 billing. Pod-minutes/throughput bắt đầu từ workload. SQS xấp xỉ, histogram latency có thể chứa error/duplicate và thiếu Pod sống ngắn. `collection-summary.md`, `report.json`, `events/collect-worker-samples.jsonl` và `events/collect-topology-samples.jsonl` là bằng chứng; collector không tự khẳng định lượt hợp lệ hoặc thu đủ log Pod biến mất. Ghi timestamps, node, image digest, bất thường và validity trong `notes.md`.

Dùng `compare` trên report của ba mức cùng profile, workload, worker/queue và cửa sổ; đối chiếu desired/ready replicas, backlog, drain, throughput, p95 và Pod-minutes. Nếu thay queue target so với 5/10/20 phải sửa manifest, mapping kiểm tra và ghi lại thiết kế trước khi chạy.

## 5. Khôi phục

Sau drain, kiểm tra ownership tài nguyên `e7-orders-sqs`, `e7-orders-sqs-auth`, HPA và baseline trước khi xóa; chỉ xóa resource thuộc lượt này:

```bash
kubectl --context twolevel-dev -n retailstore get scaledobject e7-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e7-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e7-orders-keda-hpa --ignore-not-found
# Nếu HPA còn tồn tại:
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e7-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore get triggerauthentication e7-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e7-orders-sqs-auth --wait=true
test -s ../../.generated/e7/orders-original-values.yaml && test -s ../../.generated/e7/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e7/orders-original-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e7/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
```

Xác minh worker đã rời node của thí nghiệm, node không còn workload cần giữ và Helm release đúng owner, rồi mới gỡ NodePool (có thể chấm dứt EC2):

```bash
helm status e7-capacity -n karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e7-orders -o wide
helm uninstall e7-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e7-orders
```

Giữ baseline khi chưa xác nhận phục hồi. Kiểm tra EC2 thực sự đã thu hồi; không gỡ node hệ thống hoặc controller chung.
