# E1 — Warm vs Elastic với KEDA và Karpenter

E1 so sánh cùng worker, KEDA, Karpenter và workload trong hai điều kiện đầu: **warm** có sẵn node worker và đủ capacity cho nhu cầu dự kiến; **elastic** bắt đầu với một worker Ready, không chuẩn bị thêm capacity, và cần quan sát Pod Unschedulable do thiếu capacity cùng NodeClaim/node mới. Kiểm tra hai điều kiện trước khi kết luận; một lượt không tạo node mới vẫn là dữ liệu quan sát nhưng không chứng minh đường provisioning.

Mọi lệnh dưới đây chạy từ `experiments/E1` trong Git Bash. Mỗi terminal đều đặt thư mục này; không cần `cd` sang E khác. File trong thư mục này là bộ E1 riêng. Chart hạ tầng và chart ứng dụng vẫn dùng từ project.

## File và thông số

| File | Vai trò |
|---|---|
| `karpenter-values.yaml` | NodePool/NodeClass `e1-orders`, On-Demand, `c7i-flex.large`, consolidation `Never` |
| `autoscaled-values.yaml`, `keda.yaml` | Worker chọn NodePool E1; KEDA SQS min 1, max 10, queueLength 10, polling 30s, cooldown 300s |
| `warm-capacity.yaml` | 10 Pod tạm giữ chỗ để chuẩn bị warm; requests 500m/256Mi khớp overlay worker E1 |
| `stead.js`, `step.js`, `burst.js`, `workload-common.js` | workload E0 tại chỗ: Steady 5/s 2 phút; Step 5→10→15→20→15→10→5/s, mỗi bậc 1 phút; Burst 5/s 1 phút → 40/s 30 giây → 5/s 1 phút |
| `run.py`, `run.sh` | Tạo hồ sơ/kiểm tra target và các lệnh tắt; `run.sh` không apply hoặc xóa tài nguyên |
| `collect.py`, `snapshot.py` | `collect.py` thu SQS, Prometheus, Pod, Node/NodeClaim/event; `snapshot.py` là công cụ Kubernetes chỉ đọc bổ sung, không bắt buộc |
| `report.py`, `compare.py` | Tóm tắt một lượt và so sánh các report cùng workload/cửa sổ |

Các giá trị trên là **cấu hình trong repo**; kiểm tra cấu hình thực tế trên cluster trước mỗi lượt. E1 đặt CPU request worker thành **500m** thay cho mức 128m đã dùng trong E0, nhằm làm rõ giới hạn scheduling trên node 2 vCPU; cả hai nhánh đều dùng cùng request này. Thay đổi request có thể ảnh hưởng chia sẻ CPU, nên cần pilot lại throughput trước khi dùng ước lượng μ từ E0. Cấu hình vẫn không bảo đảm workload sẽ tạo Pending: phải kiểm chứng bằng dữ liệu. Hai nhánh phải cùng image/digest, requests/limits, concurrency, queue, KEDA, loại node và workload; ghi cả khác biệt không kiểm soát. KEDA/Karpenter, API và monitoring cần node hệ thống độc lập. Kiểm tra quota, IAM, subnet, AMI, IP và chi phí; warm có thể tạo nhiều node, và `Never` giữ node sau khi hết tải.

## 1. Kiểm tra và lưu baseline

Cần `kubectl`, Helm 4, AWS CLI, Python 3, k6, Prometheus và quyền truy cập SQS/EKS. Kiểm tra context/region, thông số trong các YAML và Orders chart. Dừng nếu có HPA hoặc ScaledObject khác đang quản lý `orders-worker`; không xóa tài nguyên không thuộc lượt này. Kiểm tra queue/DLQ rỗng và không có producer/consumer khác. Các tên E1 phải chưa được tài nguyên khác sử dụng.

```bash
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects
kubectl --context twolevel-dev get nodes -o wide
kubectl --context twolevel-dev get nodepool e1-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e1-orders --ignore-not-found
kubectl --context twolevel-dev -n retailstore get scaledobject e1-orders-sqs --ignore-not-found
kubectl --context twolevel-dev -n retailstore get triggerauthentication e1-orders-sqs-auth --ignore-not-found
helm status e1-capacity -n karpenter --kube-context twolevel-dev
```

`helm status` có thể báo release chưa tồn tại. Kiểm tra thêm IAM KEDA, queue, monitoring và requests worker. Lưu baseline riêng; không ghi đè file có sẵn:

```bash
umask 077
mkdir -p ../../.generated/e1
 test ! -e ../../.generated/e1/orders-original-values.yaml && helm get values orders \
  -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e1/orders-original-values.yaml
 test ! -e ../../.generated/e1/orders-original-replicas.txt && kubectl --context twolevel-dev \
  -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e1/orders-original-replicas.txt
 test -s ../../.generated/e1/orders-original-values.yaml && test -s ../../.generated/e1/orders-original-replicas.txt
```

Dừng nếu bất kỳ bước lưu nào thất bại. Không purge queue. Lưu riêng giá trị thực tế, versions/commit, image digest, loại node/AZ, queue và điều kiện capacity vào `notes.md` của từng lượt.

## 2. Chuẩn bị hai nhánh

Tạo NodePool E1 một lần sau khi xác nhận các tên và release chưa tồn tại:

```bash
helm template e1-capacity ../../kubernetes/charts/platform-config \
  -n karpenter -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e1-capacity ../../kubernetes/charts/platform-config \
  -n karpenter --kube-context twolevel-dev \
  -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e1-orders nodepool/e1-orders --timeout=900s
```

**Warm:** sau khi xác nhận requests của `warm-capacity.yaml` khớp worker và quota đủ, chuẩn bị node rồi xóa Pod giữ chỗ. Kiểm tra cả allocatable, requests đã dùng, Pod/IP còn trống và số node còn Ready sau khi xóa.

```bash
kubectl --context twolevel-dev -n retailstore apply -f ./warm-capacity.yaml
kubectl --context twolevel-dev -n retailstore rollout status deployment/e1-warm-capacity --timeout=900s
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e1-orders -o wide
kubectl --context twolevel-dev -n retailstore get deployment e1-warm-capacity --show-labels
kubectl --context twolevel-dev -n retailstore delete deployment e1-warm-capacity --wait=true
kubectl --context twolevel-dev -n retailstore get pods -l app=e1-warm-capacity
```

**Elastic:** không tạo warm-capacity. Bắt đầu từ NodePool E1 chưa có node worker nhàn rỗi; sau bước triển khai bên dưới, chờ đúng một worker Ready. Ghi capacity còn lại. Nếu workload không tạo được Pod Unschedulable và node mới, không mặc định lượt đã chứng minh provisioning; pilot và điều chỉnh thiết kế trước lượt chính thức. Để đổi nhánh phải xử lý/khôi phục tài nguyên của lượt trước, không để node warm còn lại làm sai điều kiện elastic.

Áp dụng worker và KEDA giống nhau ở cả hai nhánh:

```bash
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart \
  -n retailstore --kube-context twolevel-dev \
  -f ../../.generated/e1/orders-original-values.yaml -f ./autoscaled-values.yaml \
  --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e1-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects,deployments,pods -o wide
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e1-orders -o wide
```

`--server-side=false` dành cho Helm 4; nếu vẫn có conflict/rollout lỗi, dừng và kiểm tra managed fields, autoscaler và baseline trước khi tiếp tục. Không dùng `--force-conflicts` tự động. Chờ KEDA ổn định ở 1 desired/Ready worker, queue drain, Prometheus có target worker UP. Ghi điều kiện đầu và xác nhận warm đủ capacity hoặc elastic chưa giữ node dự phòng; `collect.py --check` không thể tự chứng minh toàn bộ các điều kiện này.

## 3. Chạy một lượt với hai terminal

Ví dụ **warm-step-r01**. Đổi `warm` thành `elastic`, `step` thành `burst`/`steady`, và đổi attempt ở cả `RUN_DIR` lẫn lệnh init cho các lượt tiếp theo. Không ghi đè thư mục cũ. Lệnh sau chạy trong E1.

**Terminal 1:** mở Prometheus port-forward và giữ tiến trình nền, sau đó tạo hồ sơ và bắt đầu thu:

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E1/E1-warm-step-r01
bash ./run.sh init --variant warm --profile step --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Chờ dòng `ĐANG THU`, sau đó đợi ít nhất **75 giây baseline** để report mặc định tính cả idle. Nếu `--check` báo lỗi, xử lý trước khi chạy collector và workload.

**Terminal 2:** mở Orders port-forward, rồi phát tải đúng profile và RUN_DIR:

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E1/E1-warm-step-r01
bash ./run.sh load step "$RUN_DIR"
```

`load` kiểm tra metadata/profile và collector đang chạy; từ chối ghi đè summary. Sau khi k6 dừng, tiếp tục thu ít nhất **60 giây**, lâu hơn nếu queue chưa drain. Kiểm tra nhiều mẫu visible/in-flight/delayed, DLQ và job; khi đã quan sát đủ, nhấn **Ctrl+C một lần** tại terminal collector, chờ quá trình xuất Prometheus kết thúc. Mỗi terminal dừng port-forward của chính nó khi xong bằng `kill "$PROM_PID"` hoặc `kill "$ORDERS_PID"` tương ứng.

## 4. Báo cáo

```bash
RUN_DIR=../results/E1/E1-warm-step-r01
bash ./run.sh report --run-dir "$RUN_DIR"
```

Mặc định report dùng 60 giây trước tải cho Node-minutes và 60 giây sau tải; có thể đổi `--before`/`--after` nhưng phải thu đủ dữ liệu và giữ cùng cửa sổ khi so sánh. Node-minutes xấp xỉ từ các mẫu node Kubernetes thuộc `e1-orders`, gồm idle trong cửa sổ, không phải thời gian EC2 tính phí; Pod-minutes và metric xử lý tính từ lúc bắt đầu tải. Thời gian chuẩn bị warm trước cửa sổ được ghi riêng. Báo cáo không ghi đè `report.json` có sẵn.

```bash
bash ./run.sh compare ../results/E1/E1-warm-step-r01/report.json \
  ../results/E1/E1-elastic-step-r01/report.json
```

Chỉ so sánh cùng profile, thông số workload, cấu hình worker/queue và cửa sổ. Kiểm tra `collection-summary.md`, `report.json`, `events/collect-topology-samples.jsonl`, Pod conditions và scheduler events để xác định Pending do thiếu capacity và liên kết Pod/NodeClaim/node; các timestamp mẫu có sai số, `N/A` là thiếu dữ liệu chứ không phải 0. SQS là ước lượng; percentile histogram có thể gồm error/duplicate và thiếu Pod sống ngắn; counters không thay cho đối chiếu job ID. Collector không tự xác nhận lượt hợp lệ hay thu đủ log mọi Pod đã biến mất. Đánh giá thủ công và ghi bằng chứng, lý do, lỗi, dropped iterations và drain trong `notes.md`.

Theo kế hoạch nên có ba lượt hợp lệ cho mỗi nhánh × profile khi điều kiện cho phép; Step/Burst là chính, Steady làm tham chiếu. Có thể dùng lượt E2 cho elastic nếu workload, điều kiện đầu và cửa sổ trùng; ghi run ID nguồn.

## 5. Khôi phục

Sau khi dừng tải và xác nhận drain, kiểm tra lại owner và chắc chắn chỉ tài nguyên E1 đang trỏ tới worker. Các lệnh sau chỉ dành cho tài nguyên do lượt này tạo; nếu owner/tên khác hoặc baseline thiếu, dừng để kiểm tra.

```bash
kubectl --context twolevel-dev -n retailstore get scaledobject e1-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e1-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e1-orders-keda-hpa --ignore-not-found
# Nếu HPA còn tồn tại, chờ xóa trước bước tiếp theo:
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e1-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore get triggerauthentication e1-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e1-orders-sqs-auth --wait=true
 test -s ../../.generated/e1/orders-original-values.yaml && test -s ../../.generated/e1/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart \
  -n retailstore --kube-context twolevel-dev -f ../../.generated/e1/orders-original-values.yaml \
  --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e1/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
```

Kiểm tra worker đã rời node E1, các node không còn workload cần giữ và release thuộc E1 trước khi gỡ NodePool. Gỡ release có thể chấm dứt EC2 và làm gián đoạn Pod trên node đó:

```bash
helm status e1-capacity -n karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e1-orders -o wide
helm uninstall e1-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e1-orders
```

Giữ file baseline và kết quả nếu còn lượt khác hoặc khôi phục chưa hoàn tất. Kiểm tra node/NodeClaim và EC2 thực tế đã được thu hồi; không gỡ KEDA/Karpenter controller hay node hệ thống.

## 6. Kết quả E1

E1 đã chạy hai lượt cho mỗi nhánh và profile. Warm bắt đầu với **4 node E1**, Elastic với **1 node E1**; cả hai bắt đầu với **1 worker Ready**. Các lượt dùng cùng image worker, CPU request `500m`, concurrency `1` và cùng workload trong mỗi profile. Step tăng từ 5 lên 20 request/s theo bậc; Burst tăng từ 5 lên 40 request/s trong 30 giây rồi trở về 5 request/s.

| Profile | Nhánh | Lượt | Node E1 đầu → cao nhất | Đỉnh queue ≈ | p95 E2E ≈ (s) | Node-phút ≈ |
|---|---|---|---:|---:|---:|---:|
| Step | Warm | r01 | 4 → 4 | 50 | 1,39 | 36,00 |
| Step | Warm | r02 | 4 → 4 | 103 | 4,50 | 36,01 |
| Step | Elastic | r01 | 1 → 1 | 24 | 0,25 | 9,00 |
| Step | Elastic | r02 | 1 → 2 | 47 | 1,11 | 14,91 |
| Burst | Warm | r01 | 4 → 4 | 626 | 27,02 | 18,00 |
| Burst | Warm | r02 | 4 → 4 | 545 | 18,51 | 18,02 |
| Burst | Elastic | r01 | 1 → 4 | 881 | 53,80 | 8,27 |
| Burst | Elastic | r02 | 1 → 4 | 714 | 29,09 | 8,39 |

Đỉnh queue là tổng visible và in-flight lớn nhất quan sát được từ các mẫu SQS. p95 là ước lượng từ histogram E2E của worker. Node-phút tính theo node Kubernetes thuộc NodePool E1, trong cửa sổ từ 60 giây trước đến 60 giây sau tải; **không phải chi phí EC2** và chưa bao gồm toàn bộ thời gian chuẩn bị hoặc giữ node ngoài cửa sổ.

Ở Burst, cả hai lượt Elastic có Pod không xếp lịch được do thiếu CPU request và Karpenter tạo thêm ba node. Theo mẫu collector, Warm đạt 10 worker Ready sớm hơn khoảng **39 giây ở r01** và **34 giây ở r02**. Warm vẫn có backlog vì việc scale và khởi động Pod cần thời gian. Ở Step, Elastic r01 không cần node mới, còn r02 tạo thêm một node; hai lượt Elastic có p95 và đỉnh queue quan sát thấp hơn Warm.

Cả tám lượt có 100% request được API chấp nhận theo check k6, nhưng điều này không xác nhận mọi job đã hoàn thành. Counter success chưa khớp số job được nhận và có thể thiếu dữ liệu từ Pod mới hoặc sống ngắn; chưa đối soát theo job ID. SQS và histogram là ước lượng, CPU chưa đủ dữ liệu đồng đều để so sánh chắc chắn. Các report vẫn ghi `validity: not_assessed`; cần xem [kết quả gốc](../results/E1/) và hoàn thiện `notes.md` khi đánh giá chính thức.

### Trung bình và kết luận

Bảng sau lấy **trung bình số học của hai lượt** cho từng nhánh và profile; đây là kết quả thăm dò, chưa đủ để khẳng định khác biệt ổn định.

| Profile | p95 Warm / Elastic ≈ (s) | Đỉnh queue Warm / Elastic ≈ | Node-phút Warm / Elastic ≈ | Kết luận từ các lượt đã chạy |
|---|---:|---:|---:|---|
| Step | 2,94 / 0,68 | 76,5 / 35,5 | 36,01 / 11,96 | Elastic có p95 và đỉnh queue quan sát thấp hơn; Warm giữ nhiều capacity hơn. |
| Burst | 22,77 / 41,45 | 585,5 / 797,5 | 18,01 / 8,33 | Warm đạt p95 và đỉnh queue thấp hơn, đổi lại sử dụng nhiều node-phút hơn. |
