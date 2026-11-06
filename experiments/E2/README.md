# E2 — KEDA + Karpenter: đường co giãn hai tầng

E2 quan sát từ tải/backlog tới KEDA tăng worker, Pod không lập lịch được do thiếu capacity, NodeClaim mới, Node Ready và worker Ready. Không giữ sẵn node worker dự phòng. Cấu hình E2 cho phép worker về 0; khi bắt đầu một lượt có thể có 0 hoặc 1 worker Ready. Không mặc định sự kiện xảy ra: xác minh Pod, nguyên nhân, NodeClaim và node cùng lượt. Không có Pending hoặc node mới vẫn là dữ liệu quan sát nhưng không chứng minh đường provisioning.

Mọi lệnh bên dưới thực hiện từ `experiments/E2` trong **mỗi** terminal Git Bash. Không cần chạy file trong thư mục E khác hay thư mục dùng chung. Chart hạ tầng và chart Orders là thành phần của project.

| File | Chức năng |
|---|---|
| `karpenter-values.yaml` | NodePool/NodeClass `e2-orders`, On-Demand `c7i-flex.large`, consolidation `1m` |
| `autoscaled-values.yaml`, `keda.yaml` | Worker chọn NodePool E2; CPU request 500m, KEDA SQS min 0/max 10, queueLength 10, polling 30s, cooldown 300s |
| `stead.js`, `step.js`, `burst.js`, `workload-common.js` | Workload tại chỗ: Steady 5/s 2 phút; Step 5→10→15→20→15→10→5/s, mỗi bậc 1 phút; Burst 5/s 1 phút → 40/s 30 giây → 5/s 1 phút |
| `run.py`, `run.sh`, `collect.py`, `snapshot.py` | Hồ sơ, lệnh tắt, thu SQS/Prometheus/Pod/NodeClaim/event; snapshot là tùy chọn |
| `report.py`, `timeline.py`, `compare.py` | Báo cáo từng lượt, liệt kê mốc ứng viên và tổng hợp các lượt cùng profile/cửa sổ |

Các cấu hình là **đề xuất trong repo, chưa được xác nhận trên cluster**. CPU request 500m khác E0 128m, cần pilot lại throughput. Không quy định bắt buộc Karpenter phải tạo node nếu còn capacity phù hợp. API, KEDA, Karpenter và monitoring cần node hệ thống độc lập; kiểm tra quota, IAM, subnet, AMI và chi phí trước khi chạy.

E2 mặc định `minReplicaCount=0` và consolidation `1m`; E1 hiện dùng min 1 và consolidation `Never`. Vì vậy không dùng lại lượt E2 làm nhánh elastic của E1 với hai cấu hình mặc định này; chỉ cân nhắc khi đã thực sự thống nhất cấu hình, điều kiện đầu và cửa sổ đo, đồng thời lưu run ID nguồn.

## 1. Kiểm tra, lưu baseline và chuẩn bị

Cần Python 3, kubectl, Helm 4, AWS CLI, k6, Prometheus và quyền đọc SQS. Xác nhận context/region, queue/DLQ đã drain, không có producer/consumer ngoài thí nghiệm. Dừng nếu HPA hoặc ScaledObject khác quản lý `orders-worker`; không tự xóa tài nguyên không thuộc E2. Kiểm tra release, NodePool, NodeClass và tên tài nguyên E2 chưa bị sử dụng.

```bash
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects
kubectl --context twolevel-dev get nodes -o wide
kubectl --context twolevel-dev get nodepool e2-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e2-orders --ignore-not-found
kubectl --context twolevel-dev -n retailstore get scaledobject e2-orders-sqs --ignore-not-found
kubectl --context twolevel-dev -n retailstore get triggerauthentication e2-orders-sqs-auth --ignore-not-found
helm status e2-capacity -n karpenter --kube-context twolevel-dev
```

Lưu giá trị và replica gốc, không ghi đè; dừng nếu lệnh nào thất bại:

```bash
umask 077
mkdir -p ../../.generated/e2
test ! -e ../../.generated/e2/orders-original-values.yaml && helm get values orders \
  -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e2/orders-original-values.yaml
test ! -e ../../.generated/e2/orders-original-replicas.txt && kubectl --context twolevel-dev \
  -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e2/orders-original-replicas.txt
test -s ../../.generated/e2/orders-original-values.yaml && test -s ../../.generated/e2/orders-original-replicas.txt
```

Sau khi đã xác nhận không autoscaler khác và queue rỗng, chủ động đưa worker về 0 trước khi đổi placement. Việc này tạm ngừng xử lý worker, không thực hiện nếu còn công việc cần xử lý.

```bash
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas=0
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=300s
helm template e2-capacity ../../kubernetes/charts/platform-config -n karpenter \
  -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e2-capacity ../../kubernetes/charts/platform-config -n karpenter --kube-context twolevel-dev \
  -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e2-orders nodepool/e2-orders --timeout=900s
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev \
  -f ../../.generated/e2/orders-original-values.yaml -f ./autoscaled-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e2-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects,deployments,pods -o wide
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e2-orders -o wide
```

Helm 4 `--server-side=false` không bảo đảm xử lý được mọi conflict: nếu lỗi, dừng và kiểm tra managed fields. Không tự dùng force-conflicts. Đợi worker về 0 hoặc ổn định ở 1, kiểm tra node và capacity thực tế; consolidation có thể cần thời gian và không phải đảm bảo node về 0. Ghi đầu vào, node, worker, image/digest, thiết lập queue, workload và mốc UTC trong notes.

## 2. Một lượt đo với hai terminal

Ví dụ `elastic-step-r01`. Đổi profile (`step`, `burst`, `steady`) và attempt cho từng lượt. Hai terminal đều ở E2. **Terminal 1:**

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E2/E2-elastic-step-r01
bash ./run.sh init --variant elastic --profile step --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Sau khi thấy `ĐANG THU`, chờ ít nhất 75 giây baseline. `--check` xác nhận KEDA, SQS, worker và kết nối Prometheus, nhưng không tự kết luận capacity hay quyền của các thành phần.

**Terminal 2:**

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E2/E2-elastic-step-r01
bash ./run.sh load step "$RUN_DIR"
```

Không ghi đè summary. Khi k6 dừng, thu thêm ít nhất 60 giây và lâu hơn nếu chưa drain. Quan sát nhiều mẫu visible/in-flight/delayed, DLQ và số job hoàn thành; nhấn Ctrl+C một lần tại collector rồi chờ xuất xong. Dừng từng port-forward bằng `kill "$PROM_PID"` hoặc `kill "$ORDERS_PID"` ở terminal tương ứng.

## 3. Báo cáo và kiểm chứng timeline

```bash
RUN_DIR=../results/E2/E2-elastic-step-r01
bash ./run.sh report --run-dir "$RUN_DIR"
bash ./run.sh timeline --run-dir "$RUN_DIR"
```

`report.json` mặc định dùng 60 giây trước/sau tải cho Node-minutes; giữ cửa sổ giống nhau giữa lượt. Node-minutes là ước lượng thời gian node Kubernetes thuộc `e2-orders` hiện diện, không phải EC2 billing. `timeline` in các mốc ứng viên: Pod Unschedulable, NodeClaim, Node Ready, Pod Ready. Mốc lấy mẫu có sai số; đối chiếu Pod UID, scheduler event, NodeClaim `providerID`/`nodeName` và Node `provider_id` để xác nhận cùng chuỗi. Một danh sách rỗng cũng có thể do sự kiện ngắn hơn chu kỳ lấy mẫu. Ghi N/A nếu thiếu bằng chứng; không coi FailedScheduling do IAM, quota, taint hoặc lỗi khác là thiếu capacity.

```bash
bash ./run.sh compare ../results/E2/E2-elastic-step-r01/report.json ../results/E2/E2-elastic-step-r02/report.json
```

SQS và histogram/counters là ước lượng; percentile có thể gồm error/duplicate, không thay đối chiếu job ID. Kiểm tra `collection-summary.md`, `events/collect-worker-samples.jsonl`, `events/collect-topology-samples.jsonl`, dropped iterations, lỗi, DLQ và drain; ghi validity trong notes. Pilot trước, sau đó nên có ba lượt hợp lệ/profile khi điều kiện cho phép.

## 4. Khôi phục

Dừng tải và đợi drain, kiểm tra ownership và controller còn quản lý worker. Chỉ xóa tài nguyên E2 do lượt này tạo. Nếu owner/baseline không khớp, dừng.

```bash
kubectl --context twolevel-dev -n retailstore get scaledobject e2-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e2-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e2-orders-keda-hpa --ignore-not-found
# Nếu HPA vẫn còn:
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e2-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore get triggerauthentication e2-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e2-orders-sqs-auth --wait=true
test -s ../../.generated/e2/orders-original-values.yaml && test -s ../../.generated/e2/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev \
  -f ../../.generated/e2/orders-original-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e2/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
```

Kiểm tra worker đã rời node E2, node không còn workload cần giữ và release đúng owner trước khi gỡ NodePool. Lệnh gỡ có thể chấm dứt EC2 và các Pod trên node:

```bash
helm status e2-capacity -n karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e2-orders -o wide
helm uninstall e2-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e2-orders
```

Giữ baseline nếu khôi phục chưa thành công; kiểm tra EC2 thực tế đã thu hồi. Không gỡ controller hay node hệ thống.
