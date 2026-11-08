# E3 — CPU-HPA vs KEDA trên Karpenter

**Cập nhật 08/11/2026:** đã bổ sung tám lượt Step/Burst r03–r04; mỗi nhánh hiện có
bốn lượt cho Step và Burst, hai lượt cho Steady. Xem [báo cáo mở rộng và biểu đồ](REPEATS-REPORT.md)
và [trạng thái các lượt mới](REPEATS-STATUS.md). Báo cáo 12 lượt ngày 07/11 bên dưới được giữ riêng.

Hướng dẫn thao tác sau E0/E1, thu số liệu và reset giữa các lượt: [RUNBOOK.md](RUNBOOK.md).

Nếu upgrade làm API/worker thiếu cấu hình DB hoặc TLS, xem [RECOVERY.md](RECOVERY.md)
và kiểm tra chart local có đủ tính năng như chart đã triển khai trước đó.

Các lượt đã đánh giá được tóm tắt trong [RESULTS.md](RESULTS.md).

Đã hoàn thành **12/12 lượt** ngày 2026-11-07. Kết quả và biểu đồ được lưu trong [FINAL-REPORT.md](FINAL-REPORT.md).
Đã khôi phục E1 và thu hồi EC2 E3; xem [CLEANUP.md](CLEANUP.md).
Tài liệu thao tác bên dưới dành cho một đợt chạy mới; không chạy lại lên kết quả đã có.

Đợt chạy hiện tại chọn **hai lượt/nhánh/profile**, theo thứ tự Step → Burst → Steady;
xem trạng thái và thứ tự các lượt trong [RUNS.md](RUNS.md).

E3 so sánh hai bộ điều khiển worker trên cùng workload. Mỗi nhánh bắt đầu với **một node worker Ready được giữ sẵn** và một worker Ready; capacity còn trống, image, requests/limits, concurrency, queue, `min/max`, node type và workload phải tương đương. Karpenter vẫn được mở rộng node khi cần. Chỉ một controller độc lập quản lý worker mỗi lượt: HPA do KEDA tạo thuộc nhánh KEDA.

Mọi lệnh dưới đây chạy từ `experiments/E3` trong **mỗi** terminal Git Bash. E3 có file riêng, không cần chạy script từ thư mục E khác hoặc thư mục dùng chung; chart hạ tầng và ứng dụng dùng từ project.

| File | Chức năng |
|---|---|
| `karpenter-values.yaml`, `warm-capacity.yaml` | NodePool `e3-orders` On-Demand `c7i-flex.large`, consolidation `Never`; một Pod tạm để giữ sẵn một node |
| `autoscaled-values.yaml` | Worker chọn NodePool E3, CPU request 500m, memory request 256Mi |
| `hpa.yaml`, `keda.yaml` | HPA CPU target 60%, hoặc KEDA SQS queueLength 10; cả hai min 1/max 10 |
| `stead.js`, `step.js`, `burst.js`, `workload-common.js` | Steady 5/s 2 phút; Step 5→10→15→20→15→10→5/s, mỗi bậc 1 phút; Burst 5/s 1 phút → 40/s 30 giây → 5/s 1 phút |
| `run.py`, `run.sh`, `collect.py`, `snapshot.py` | Hồ sơ, lệnh tắt và thu SQS, Prometheus, Pod, NodeClaim, node và event |
| `report.py`, `compare.py` | Báo cáo từng lượt và so sánh HPA/KEDA cùng profile/cửa sổ |

Các cấu hình này đã được kiểm tra trên cluster trong đợt ngày 2026-11-07; điều kiện và giới hạn được ghi trong báo cáo. CPU request 500m khác 128m của E0; HPA target 60% được tính theo request này. Một node Ready không tự chứng minh capacity trống tương đương: kiểm tra CPU, memory, Pod/IP trống và image cache từng nhánh. Pod Pending và node mới được ghi nhận; chênh lệch kết quả có thể bao gồm ảnh hưởng provisioning. KEDA/Karpenter, API và monitoring cần node hệ thống độc lập. Kiểm tra quota, IAM, subnet và chi phí; `Never` có thể giữ node sau khi tải đã dừng.

## 1. Kiểm tra và lưu baseline

Cần Python 3, kubectl, Helm 4, AWS CLI, k6 và Prometheus. Kiểm tra context/region, queue/DLQ rỗng và không có producer/consumer ngoài thí nghiệm. Dừng nếu HPA hoặc ScaledObject khác quản lý `orders-worker`; chỉ một trong `hpa.yaml` và `keda.yaml` được áp dụng. Xác nhận các tên E3 và release chưa được dùng:

```bash
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects
kubectl --context twolevel-dev get nodes -o wide
kubectl --context twolevel-dev get nodepool e3-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e3-orders --ignore-not-found
kubectl --context twolevel-dev -n retailstore get hpa e3-orders-cpu --ignore-not-found
kubectl --context twolevel-dev -n retailstore get scaledobject e3-orders-sqs --ignore-not-found
kubectl --context twolevel-dev -n retailstore get triggerauthentication e3-orders-sqs-auth --ignore-not-found
helm status e3-capacity -n karpenter --kube-context twolevel-dev
```

Lưu baseline riêng, không ghi đè; dừng nếu bước nào thất bại:

```bash
umask 077
mkdir -p ../../.generated/e3
test ! -e ../../.generated/e3/orders-original-values.yaml && helm get values orders \
  -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e3/orders-original-values.yaml
test ! -e ../../.generated/e3/orders-original-replicas.txt && kubectl --context twolevel-dev \
  -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e3/orders-original-replicas.txt
test -s ../../.generated/e3/orders-original-values.yaml && test -s ../../.generated/e3/orders-original-replicas.txt
```

## 2. Chuẩn bị node và một controller

Sau khi kiểm tra quota và tên release/NodePool/NodeClass E3 chưa tồn tại, tạo NodePool, tạm tạo một Pod để provision một node, sau đó xóa Pod tạm. Kiểm tra chỉ còn đúng một node E3 Ready trước mỗi lượt; nếu còn nhiều node sau lượt trước, khôi phục rồi chuẩn bị lại.

```bash
helm template e3-capacity ../../kubernetes/charts/platform-config -n karpenter \
  -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e3-capacity ../../kubernetes/charts/platform-config -n karpenter --kube-context twolevel-dev \
  -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e3-orders nodepool/e3-orders --timeout=900s
kubectl --context twolevel-dev -n retailstore apply -f ./warm-capacity.yaml
kubectl --context twolevel-dev -n retailstore rollout status deployment/e3-warm-capacity --timeout=900s
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e3-orders -o wide
kubectl --context twolevel-dev -n retailstore get deployment e3-warm-capacity --show-labels
kubectl --context twolevel-dev -n retailstore delete deployment e3-warm-capacity --wait=true
kubectl --context twolevel-dev -n retailstore get pods -l app=e3-warm-capacity
```

Triển khai worker giống nhau cho hai nhánh. Đợt này dùng chart trích từ Helm revision 21
vì chart backend local thiếu Secret DB/TLS/ServiceAccount; xem [RECOVERY.md](RECOVERY.md).
Kiểm tra artifact chart và baseline đã chọn trước khi chạy:

```bash
test -s ../../.generated/e3/orders-chart-revision21/Chart.yaml
helm upgrade orders ../../.generated/e3/orders-chart-revision21 -n retailstore --kube-context twolevel-dev \
  -f ../../.generated/e3/orders-original-values.yaml -f ./autoscaled-values.yaml --server-side=false --wait --timeout 900s
```

Helm 4 `--server-side=false` không xử lý được mọi conflict; nếu lỗi, dừng kiểm tra managed fields, baseline và controller. **Chọn đúng một** trong hai lệnh, không chạy cả hai:

```bash
# Nhánh HPA:
kubectl --context twolevel-dev -n retailstore apply -f ./hpa.yaml
# HOẶC nhánh KEDA:
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e3-orders-sqs --timeout=300s
```

Lệnh `wait scaledobject` chỉ dành cho nhánh KEDA. Kiểm tra đúng controller, HPA metric hoạt động, một node E3 Ready, một worker desired/Ready, queue/DLQ rỗng và Prometheus worker UP. Ghi spare capacity, node type/AZ, image/digest, phiên bản/cấu hình và các mốc UTC vào notes. Chuyển nhánh chỉ sau khi dừng tải, drain, gỡ controller thuộc E3 và tái lập điều kiện đầu tương đương; nếu có nhiều node sau workload, khôi phục rồi chuẩn bị lại một node.

## 3. Chạy một lượt với hai terminal

Ví dụ `hpa-step-r01`. Các terminal đều ở E3. Đổi variant `hpa`/`keda`, profile và attempt cho từng lượt.

**Terminal 1:**

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E3/E3-hpa-step-r01
bash ./run.sh init --variant hpa --profile step --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

`--check` yêu cầu controller phù hợp, chính xác một node E3 Ready, một worker Ready, queue/DLQ rỗng và worker target Prometheus UP; kiểm tra spare capacity vẫn cần thực hiện thủ công. Chờ `ĐANG THU` rồi ít nhất 75 giây baseline.

**Terminal 2:**

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E3/E3-hpa-step-r01
bash ./run.sh load step "$RUN_DIR"
```

Đợi ít nhất 60 giây sau khi k6 dừng và lâu hơn nếu chưa drain. Kiểm tra nhiều mẫu visible/in-flight/delayed, DLQ và job; nhấn Ctrl+C một lần tại collector và chờ xuất xong. Mỗi terminal dừng port-forward riêng bằng `kill "$PROM_PID"` hoặc `kill "$ORDERS_PID"`.

## 4. Báo cáo

```bash
RUN_DIR=../results/E3/E3-hpa-step-r01
bash ./run.sh report --run-dir "$RUN_DIR"
bash ./run.sh compare ../results/E3/E3-hpa-step-r01/report.json ../results/E3/E3-keda-step-r01/report.json
```

Report dùng mặc định 60 giây trước/sau workload cho Node-minutes; chỉ so sánh cùng profile, workload, cấu hình worker/queue và cửa sổ. Node-minutes là ước lượng từ node Kubernetes `e3-orders`, không phải chi phí EC2 thực tế. HPA/KEDA dùng cùng worker nhưng mức capacity trống, node type/AZ và image cache vẫn cần đối chiếu thủ công. Kiểm tra backlog, throughput, latency, CPU, desired/ready/Pending, Pod/node, NodeClaim, drain, lỗi và dropped iterations trong report và raw. Histogram/counters và SQS là ước lượng; job error/duplicate có thể xuất hiện trong histogram, không thay đối chiếu job ID. Ghi validity, nguyên nhân Pending và ảnh hưởng node mới trong notes. Pilot trước, nên có ba lượt hợp lệ mỗi nhánh/profile khi điều kiện cho phép.

## 5. Khôi phục

Sau drain, kiểm tra controller, owner và baseline. Chỉ gỡ nhánh E3 đang dùng:

```bash
# Nếu là nhánh HPA và owner đúng E3:
kubectl --context twolevel-dev -n retailstore get hpa e3-orders-cpu --show-labels
kubectl --context twolevel-dev -n retailstore delete hpa e3-orders-cpu --wait=true
# Nếu là nhánh KEDA và owner đúng E3:
kubectl --context twolevel-dev -n retailstore get scaledobject e3-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e3-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e3-orders-keda-hpa --ignore-not-found
# Chờ HPA KEDA xóa nếu vẫn tồn tại:
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e3-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore get triggerauthentication e3-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e3-orders-sqs-auth --wait=true
```

Khôi phục baseline sau khi không còn controller E3 quản lý worker:

Đây là lệnh tổng quát cho baseline không còn scaler trước E3. Riêng đợt ngày
2026-11-07 dùng bản sao E1 trong `.generated/e3/pre-e3-20261107T083008Z/` và phải
khôi phục cả ScaledObject/auth E1 (min 3/max 10); trạng thái thực tế được ghi trong
[CLEANUP.md](CLEANUP.md). Không thay bản sao đó bằng cấu hình E3 đang chạy.

```bash
test -s ../../.generated/e3/orders-original-values.yaml && test -s ../../.generated/e3/orders-original-replicas.txt
test -s ../../.generated/e3/orders-chart-revision21/Chart.yaml
helm upgrade orders ../../.generated/e3/orders-chart-revision21 -n retailstore --kube-context twolevel-dev \
  -f ../../.generated/e3/orders-original-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e3/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
```

Kiểm tra worker rời node E3, node không chứa workload cần giữ và release đúng owner trước khi gỡ; việc gỡ có thể chấm dứt EC2 và Pod trên node:

```bash
helm status e3-capacity -n karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e3-orders -o wide
helm uninstall e3-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e3-orders
```

Giữ baseline nếu khôi phục chưa hoàn tất; kiểm tra EC2 thực tế đã thu hồi. Không gỡ controller hay node hệ thống. Kết quả E1 HPA/KEDA cũ trong `experiments/results/E1-legacy` không tự coi là kết quả E3 mới.
