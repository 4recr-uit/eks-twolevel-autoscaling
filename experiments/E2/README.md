# E2 — Cold start Pod và co giãn hai tầng KEDA + Karpenter

**Câu hỏi:** Khi tải đến lúc chưa có worker nhưng đã có một node worker, Pod khởi động mất bao lâu, KEDA và Karpenter mở rộng như thế nào khi cần thêm capacity, và worker trở về 0 sau tải ra sao?

**Điều kiện đầu:** 0 worker Pod, 1 node `e2-orders` Ready được bảo vệ khỏi consolidation; hai node hệ thống chạy API, KEDA, Karpenter và monitoring. Queue và DLQ đã drain. Node sẵn làm cho cold start đầu tiên là cold start Pod trên node có sẵn; các node worker mới chỉ được tạo nếu capacity không đủ. Ghi node, capacity còn lại và timestamp thực tế trước mỗi lượt.

```text
Tải đến → cold start Pod trên node sẵn → scale-out Pod
→ nếu thiếu capacity: Pod chờ → tạo node mới → Pod Ready
→ dừng tải → queue drain → cooldown → 0 worker Pod
```

Node ban đầu có annotation `karpenter.sh/do-not-disrupt=true` nên không bị consolidation tự nguyện thu hồi; các node E2 khác vẫn có thể được thu hồi. Annotation không ngăn mọi nguyên nhân mất node. Không mặc định sẽ có Pod thiếu capacity hoặc node mới: nếu không quan sát thấy, ghi `N/A` cho các mốc tương ứng.

## Thiết kế đo và timeline

Thu ít nhất 75 giây baseline không phát tải. T0 là lúc bắt đầu phát workload của lượt đo; gauge bắt đầu hiện tại được ghi trong k6 `setup`, nên có thể lệch so với request đầu tiên. Ghi timestamp UTC, nguồn và độ phân giải cho từng mốc; khi đo provisioning, đối chiếu Pod UID, scheduler event, NodeClaim, provider ID và node tương ứng.

| Mốc | Định nghĩa |
|---|---|
| T0 | Bắt đầu phát tải. |
| T1 | Worker đầu tiên Ready trên node E2 sẵn có. |
| T2 | Quan sát Pod `Unschedulable` do thiếu capacity. |
| T3 | NodeClaim mới được tạo; đây là proxy, không phải thời điểm chính xác Karpenter bắt đầu xử lý. |
| T4 | Node mới gắn với NodeClaim Ready. |
| T5 | Pod từng chờ ở T2 Ready trên node T4, xác nhận bằng cùng Pod UID. |
| T6 | Dừng phát tải. |
| T7 | Queue drain được xác nhận qua nhiều mẫu visible/in-flight/delayed và DLQ. |
| T8 | Deployment được quan sát về 0 worker Pod sau tải. |

| Khoảng đo | Công thức |
|---|---|
| Cold start Pod trên node sẵn | `T1 − T0` |
| Provisioning node | `T4 − T3` |
| Pod khởi động trên node mới | `T5 − T4` |
| Queue drain sau tải | `T7 − T6` |
| Scale về 0 Pod sau tải | `T8 − T6` |

Thu thêm peak backlog, throughput, p95/p99 E2E, số worker và node theo thời gian; ghi rõ nguồn và cửa sổ. `T8 − T6` không phải riêng thời gian cooldown: cooldown tính từ lần cuối trigger được ghi nhận hoạt động. NodeClaim là proxy; `T4 − T3` không chứng minh toàn bộ khoảng đó gây tăng latency end-to-end.

Các mốc lấy mẫu có thể không phản ánh chính xác thứ tự thực tế. Không tính khoảng âm hoặc điền 0 khi thiếu bằng chứng; ghi `N/A`. Không quy kết Pod Pending do thiếu CPU nếu scheduler event cho thấy IAM, quota, taint hoặc nguyên nhân khác. SQS và histogram là số ước lượng.

`timeline.py` xuất các mốc T0–T8 và khoảng thời gian có thể suy ra từ mẫu; `null` nghĩa là chưa đủ bằng chứng. Mốc T2–T5 liên kết Pod và node là ứng viên, cần đối chiếu scheduler event và nguyên nhân thiếu capacity. `report.py` tính các metric tổng hợp; đối chiếu raw và bổ sung nguồn khi cần.

## Chạy lượt E2

Mọi lệnh bên dưới thực hiện từ `experiments/E2` trong **mỗi** terminal Git Bash. Không cần chạy file trong thư mục E khác hay thư mục dùng chung. Chart hạ tầng và chart Orders là thành phần của project.

**Trạng thái đã triển khai:** E2 đã được cài trên `twolevel-dev`, với 0 worker và một node E2 được bảo vệ tại lần kiểm tra gần nhất; phải kiểm tra lại trạng thái thực tế. Các lệnh `helm install` và lưu baseline bên dưới dành cho lần triển khai mới, không chạy lại nguyên xi nếu release hoặc baseline đã tồn tại.

| File | Chức năng |
|---|---|
| `karpenter-values.yaml` | NodePool/NodeClass `e2-orders`, On-Demand `c7i-flex.large`, consolidation `1m` |
| `autoscaled-values.yaml`, `keda.yaml` | Worker chọn NodePool E2; CPU request 500m, KEDA SQS min 0/max 10, queueLength 10, polling 5s, cooldown 150s |
| `burst.js`, `workload-common.js` | Workload Burst v5: 5/s 1 phút → 40/s 90 giây → 5/s 1 phút |
| `run.py`, `run.sh`, `collect.py` | Hồ sơ, lệnh tắt, thu SQS/Prometheus/Pod/NodeClaim/event |
| `report.py`, `timeline.py`, `compare.py` | Báo cáo từng lượt, liệt kê mốc ứng viên và tổng hợp các lượt cùng profile/cửa sổ |

Worker có CPU request 500m. Polling 5s chi phối việc KEDA kiểm tra trigger khi worker ở 0; khi scale từ 1 lên N, HPA có chu kỳ riêng. Cooldown 150s áp dụng khi KEDA scale worker về 0. Karpenter xét consolidation độc lập theo policy và `consolidateAfter=1m`; không suy ra node sẽ bị thu hồi đúng sau 210 giây. Kiểm tra quota, IAM, subnet, AMI và chi phí trước khi chạy.

**Workload:** Burst E2 model v5 chạy 5/s trong 1 phút → 40/s trong 90 giây → 5/s trong 1 phút. T0 là đầu pha 5/s, nên cold start tính từ lúc bắt đầu phát tải, không phải từ spike 40/s. Định trước tiêu chí nếu muốn kết luận throughput phục hồi trong pha tải cao.

Kiểm tra dropped iterations của từng lượt trước khi so sánh.

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

Helm 4 `--server-side=false` không bảo đảm xử lý được mọi conflict: nếu lỗi, dừng và kiểm tra managed fields. Không tự dùng force-conflicts. Trước mỗi lượt chính thức, đợi worker về 0, xác nhận có đúng một node E2 Ready đã được bảo vệ và queue/DLQ đã drain. Collector kiểm tra những điều kiện này; vẫn ghi node, capacity, image/digest, thiết lập queue, workload và mốc UTC trong notes.

Kiểm tra node đã có sẵn và annotation bảo vệ; thay `<ten-node-e2>` bằng đúng tên node được xác minh:

```bash
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e2-orders -o wide
kubectl --context twolevel-dev get node <ten-node-e2> -o jsonpath='{.metadata.annotations.karpenter\.sh/do-not-disrupt}'
kubectl --context twolevel-dev annotate node <ten-node-e2> karpenter.sh/do-not-disrupt="true" --overwrite
```

Nếu chưa có node E2, tạo một Pod tạm có node selector `karpenter.sh/nodepool=e2-orders` để yêu cầu capacity; sau khi xác nhận Pod đã schedule lên đúng node E2, gắn annotation cho node trước khi xóa Pod tạm. Không giữ Pod tạm trong lượt đo. Annotation chỉ bảo vệ node được gắn và node này tiếp tục phát sinh chi phí khi idle.

## 2. Một lượt đo với hai terminal

Các lệnh thu dưới đây dùng profile `burst`; giữ cùng workload và thay attempt cho từng lượt. Ví dụ cho lượt mới dùng `elastic-burst-r03`; hai terminal đều ở E2. **Terminal 1:**

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E2/E2-elastic-burst-r03
bash ./run.sh init --variant elastic --profile burst --attempt 3
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Sau khi thấy `ĐANG THU`, chờ ít nhất 75 giây baseline. `--check` xác nhận KEDA, SQS, worker và kết nối Prometheus, nhưng không tự kết luận capacity hay quyền của các thành phần.

**Terminal 2:**

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E2/E2-elastic-burst-r03
bash ./run.sh load burst "$RUN_DIR"
```

Không ghi đè summary. Khi k6 dừng, tiếp tục thu ít nhất 60 giây và đến khi queue drain và worker về 0; cooldown 150s có thể khiến thời gian cần thu lâu hơn. Quan sát nhiều mẫu visible/in-flight/delayed, DLQ, số job hoàn thành và số Pod; nhấn Ctrl+C một lần tại collector rồi chờ xuất xong. Nếu worker không về 0, ghi lý do và mốc quan sát. Dừng từng port-forward bằng `kill "$PROM_PID"` hoặc `kill "$ORDERS_PID"` ở terminal tương ứng.

## 3. Báo cáo và kiểm chứng timeline

```bash
RUN_DIR=../results/E2/E2-elastic-burst-r03
bash ./run.sh report --run-dir "$RUN_DIR"
bash ./run.sh timeline --run-dir "$RUN_DIR"
```

`report.json` mặc định dùng 60 giây trước/sau tải cho Node-minutes; giữ cửa sổ giống nhau giữa lượt. Cửa sổ đó không nhất thiết bao gồm T8 do cooldown, dù collector tiếp tục thu lâu hơn. Node-minutes là ước lượng thời gian node Kubernetes thuộc `e2-orders` hiện diện, không phải EC2 billing. `timeline` in T0–T8 và các chuỗi ứng viên; mốc lấy mẫu có sai số, cần đối chiếu Pod UID, scheduler event, NodeClaim `providerID`/`nodeName` và Node `provider_id`. Một danh sách rỗng cũng có thể do sự kiện ngắn hơn chu kỳ lấy mẫu. Ghi N/A nếu thiếu bằng chứng; không coi FailedScheduling do IAM, quota, taint hoặc lỗi khác là thiếu capacity.

```bash
bash ./run.sh compare ../results/E2/E2-elastic-burst-r01/report.json ../results/E2/E2-elastic-burst-r02/report.json
```

SQS và histogram/counters là ước lượng; percentile có thể gồm error/duplicate, không thay đối chiếu job ID. Kiểm tra `collection-summary.md`, `events/collect-worker-samples.jsonl`, `events/collect-topology-samples.jsonl`, dropped iterations, lỗi, DLQ và drain; ghi validity trong notes. Pilot trước, sau đó nên có ba lượt hợp lệ/profile khi điều kiện cho phép.

## 4. Khôi phục

Sau khi đo, có thể giữ E2 cùng node được bảo vệ cho các lượt sau; node tiếp tục phát sinh chi phí. Lệnh dưới đây chỉ dùng khi chủ ý kết thúc và gỡ E2. Trước khi khôi phục, xác định cấu hình đích và kiểm tra baseline đã lưu phù hợp với cấu hình đó.

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

Kiểm tra worker đã rời node E2, node không còn workload cần giữ và release đúng owner trước khi gỡ NodePool. Nếu muốn bỏ bảo vệ node ban đầu, kiểm tra đúng tên node rồi dùng `kubectl --context twolevel-dev annotate node <ten-node-e2> karpenter.sh/do-not-disrupt-`. Lệnh gỡ release có thể chấm dứt EC2 và các Pod trên node:

```bash
helm status e2-capacity -n karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e2-orders -o wide
helm uninstall e2-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e2-orders
```

Giữ baseline nếu khôi phục chưa thành công; kiểm tra EC2 thực tế đã thu hồi. Không gỡ controller hay node hệ thống.

## Vẽ biểu đồ E2

Từ thư mục gốc repo, cài Matplotlib và chạy script để tạo hình của lượt r02:

```bash
python -m pip install -r experiments/E2/requirements-plot.txt
python experiments/E2/visualize-scripts/plot_e2_timeline.py
```

Script đọc `report.json`, `timeline.json` và các mẫu SQS, worker, Node đã thu; không truy cập cluster. Đầu ra là `experiments/E2/figures/e2-e1-style-timeline.png` và `.svg`. Khi tạo lại hình có sẵn, thêm `--overwrite`; có thể chọn lượt hoặc thư mục xuất bằng `--run-dir` và `--output-dir`. Script `plot_e2.py` vẫn tạo phiên bản bốn hàng riêng.

Hình dùng chung trục thời gian bắt đầu từ T0 với ba hàng queue, worker desired/Ready và số Node E2 hiện diện; các pha tải mục tiêu được đánh dấu phía trên. Nhãn trên hình dùng tiếng Anh. Đường queue nối các mẫu SQS xấp xỉ để dễ theo dõi, còn worker và Node dùng đường bậc theo các mẫu quan sát. Các mốc T0–T8 được đánh dấu trực tiếp cùng thời gian tính từ T0; ý nghĩa của từng mốc nằm trong bảng timeline bên dưới. Đường gióng cuối biểu thị thời điểm lần đầu quan sát số Node giảm trong lần scale-down cuối, không phải thời điểm EC2 chấm dứt. Đường nối giữa hai mẫu không xác nhận trạng thái hoặc thời điểm chuyển tiếp chính xác; Node hiển thị là các Node thuộc NodePool E2, không tính Node hệ thống.

## 5. Kết quả thực nghiệm E2

**Phạm vi trình bày trong báo cáo NT531 và NT533:** sử dụng riêng lượt `r02`, không gộp hoặc tính trung bình với `r01`. Các kết quả của `r01` bên dưới được giữ lại để lưu lịch sử thực nghiệm.

Hai lượt [r01](../results/E2/E2-elastic-burst-r01/report.json) và [r02](../results/E2/E2-elastic-burst-r02/report.json) dùng Burst v5: 5 request/s trong 60 giây → 40 request/s trong 90 giây → 5 request/s trong 60 giây. Mỗi lượt bắt đầu với 0 worker, một node E2 Ready được bảo vệ và queue/DLQ rỗng theo mẫu. Report ghi cùng cấu hình worker và image digest; KEDA đặt min 0, max 10, polling 5 giây và cooldown 150 giây.

### Phản ứng khi tăng tải

- **Cold start:** worker đầu tiên trên node có sẵn được quan sát Ready sau 24,6 giây ở r01 và 22,9 giây ở r02, tính từ đầu pha 5 request/s. Đây là thời gian quan sát được, không phải cold start tính từ spike 40 request/s.
- **Scale-out:** cả hai lượt tạo NodeClaim đầu tiên trong pha 5 request/s, trước spike. Ở r01, thêm một NodeClaim được tạo khoảng 16,1 giây sau spike; Pod từng chờ do thiếu CPU được quan sát Ready trên node tương ứng khoảng 56,4 giây sau spike. Ở r02, NodeClaim bổ sung duy nhất được tạo khoảng 36,7 giây trước spike và không quan sát thêm NodeClaim trong pha cao. Vì vậy không quy tất cả node mới cho spike 40 request/s.
- **Queue và latency:** trong hai lượt, r02 có peak queue và p95 E2E quan sát thấp hơn r01. r02 đạt 6 worker Ready khoảng 18,8 giây sau spike; r01 đạt 6 worker Ready khoảng 28,7 giây sau spike. Khác biệt thời điểm capacity có thể góp phần, nhưng dữ liệu không xác định được nguyên nhân duy nhất hoặc cho phép khẳng định throughput đã ổn định ở 40 request/s.
- **Kết thúc tải:** hai lượt đều ghi queue và DLQ bằng 0 ở snapshot cuối, worker về 0 và node E2 ban đầu vẫn được bảo vệ. Khoảng từ khi dừng tải đến khi quan sát 0 worker không phải phép đo riêng cooldown 150 giây: cooldown được tính từ lần cuối trigger hoạt động, không nhất thiết từ lúc k6 dừng.

Cả hai lượt ghi 4.199 request được API chấp nhận, không HTTP failure và không ghi nhận dropped iterations. Report tính success bằng delta từng chuỗi Pod nên bỏ giá trị đã có ở mẫu đầu; cộng phần đó vào cho tổng mẫu cuối 4.199 ở mỗi lượt. Chưa đối chiếu job ID nên không kết luận mỗi job được xử lý đúng một lần. Xem thêm [log controller](controller-log-e2-r01-r02.jsonl), [report r01](../results/E2/E2-elastic-burst-r01/report.json) và [report r02](../results/E2/E2-elastic-burst-r02/report.json).

### Đối chiếu mục tiêu E2

Hai lượt đã quan sát được chu trình theo thiết kế E2: cold start worker trên node có sẵn; Pod chờ do thiếu CPU và được bố trí lên node E2 mới; sau tải queue drain, worker về 0 và node ban đầu vẫn được bảo vệ. Riêng r01 còn ghi nhận thêm NodeClaim trong pha 40 request/s. r02 tạo node bổ sung trước pha cao, nên không dùng r02 để minh họa việc tạo node do spike kích hoạt.

Các kết quả đáp ứng mục tiêu mô tả hành vi và đo thời gian theo mẫu của E2. Chúng chưa xác định chính xác nguyên nhân biến động giữa hai lượt, thời điểm cooldown bắt đầu hoặc throughput ổn định trong pha cao; các mốc T2–T5 là chuỗi liên kết theo Pod UID, NodeClaim và provider ID, được đối chiếu từ các nguồn lấy mẫu độc lập.

### Các mốc quan sát

Các số trong bảng là **số giây từ T0 của từng lượt**. T0 tương ứng `2026-11-07 20:10:37,905 UTC` ở r01 và `2026-11-08 08:04:35,729 UTC` ở r02; T0 và T6 lấy từ k6 setup/teardown. T2, T4 và T5 là lần đầu collector quan sát trạng thái; T3 lấy thời điểm tạo NodeClaim. Phần thập phân giúp đối chiếu timestamp, không phản ánh độ chính xác phép đo: khoảng giữa các mẫu worker có trung vị khoảng 7 giây.

| Mốc | Ý nghĩa | r01: giây từ T0 | r02: giây từ T0 |
|---|---|---:|---:|
| T0 | Bắt đầu workload | 0,00 | 0,00 |
| T1 | Worker đầu tiên Ready trên node sẵn | 24,60 | 22,91 |
| T2 | Quan sát Pod chờ do thiếu CPU | 18,02 | 29,66 |
| T3 | NodeClaim đầu tiên được tạo | 16,10 | 23,27 |
| T4 | Quan sát node tương ứng Ready | 55,30 | 67,26 |
| T5 | Quan sát Pod từng chờ Ready trên node mới | 59,73 | 72,05 |
| T6 | Kết thúc workload | 210,06 | 210,06 |
| T7 | Xác nhận queue drain | 230,85 | 234,08 |
| T8 | Quan sát worker về 0 Pod | 354,85 | 354,12 |

T2 có thể xuất hiện sau T3 trong bảng vì T2 là **lần đầu quan sát** Pod chờ, còn T3 là timestamp tạo NodeClaim; điều này không chứng minh NodeClaim được tạo trước khi Pod thực sự chờ. T1 cũng không nhất thiết xảy ra trước T2 vì nhiều Pod có thể được yêu cầu gần nhau. Các mốc T2–T5 ở đây liên kết với NodeClaim **đầu tiên**, được tạo trong pha 5 request/s.

### Các khoảng đo từ timeline

| Khoảng đo | Công thức | r01 (giây) | r02 (giây) |
|---|---|---:|---:|
| Cold start worker trên node sẵn | T1 − T0 | 24,6 | 22,9 |
| Tạo NodeClaim → quan sát node Ready | T4 − T3 | 39,2 | 44,0 |
| Quan sát node Ready → Pod từng chờ Ready | T5 − T4 | 4,4 | 4,8 |
| Dừng workload → xác nhận queue drain | T7 − T6 | 20,8 | 24,0 |
| Dừng workload → quan sát 0 worker | T8 − T6 | 144,8 | 144,1 |

Các khoảng được làm tròn theo `timeline.json` của từng lượt: [r01](../results/E2/E2-elastic-burst-r01/timeline.json), [r02](../results/E2/E2-elastic-burst-r02/timeline.json). T4 − T3 là khoảng từ lúc tạo NodeClaim đến lúc **quan sát** node Ready, không phải phép đo chính xác toàn bộ thời gian provisioning.

### Bảng kết quả và trung bình

Cột trung bình là trung bình cộng của **hai lượt**, không phải giá trị đại diện đã xác lập cho hệ thống. Trung bình p95/p99 là trung bình các percentile theo từng lượt, không phải percentile tính lại từ dữ liệu gộp. SQS là giá trị xấp xỉ; peak, số Pod/node và các mốc Ready là giá trị quan sát theo mẫu. Histogram E2E có thể gồm error/duplicate và chịu ảnh hưởng thời điểm scrape. Node-minutes đếm thời gian node E2 hiện diện từ 60 giây trước đến 60 giây sau workload, không phải thời gian tính phí EC2.

| Chỉ số | r01 | r02 | Trung bình |
|---|---:|---:|---:|
| Request API chấp nhận | 4.199 | 4.199 | 4.199 |
| Worker Ready tối đa trong mẫu | 9 | 6 | 7,5 |
| Node E2 tối đa trong mẫu | 3 | 2 | 2,5 |
| Peak queue visible + in-flight ≈ | 87 | 52 | 69,5 |
| p95 E2E ≈ (giây) | 2,384 | 0,320 | 1,352 |
| p99 E2E ≈ (giây) | 4,603 | 3,825 | 4,214 |
| Cold start Pod ≈ (giây) | 24,6 | 22,9 | 23,75 |
| Tạo NodeClaim đầu → node Ready được quan sát ≈ (giây) | 39,2 | 44,0 | 41,6 |
| Node Ready → Pod từng chờ Ready được quan sát ≈ (giây) | 4,4 | 4,8 | 4,6 |
| Dừng tải → xác nhận queue drain ≈ (giây) | 20,8 | 24,0 | 22,4 |
| Dừng tải → quan sát 0 worker ≈ (giây) | 144,8 | 144,1 | 144,45 |
| Node-minutes ≈ | 12,07 | 9,00 | 10,535 |
