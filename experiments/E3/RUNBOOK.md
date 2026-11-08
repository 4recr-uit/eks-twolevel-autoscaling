# E3 — Triển khai và thu số liệu sau E0/E1

**Kiểm tra chart trước khi upgrade:** chart backend local phải hỗ trợ
`apiServiceAccount`, `workerServiceAccount`, `databaseTLS` và Secret DB có sẵn.
Chỉ truyền lại Helm values không khôi phục được tính năng mà template local thiếu.
Sự cố ngày 2026-11-07 và lệnh sửa bằng chart đã lưu trong revision 21 được ghi tại
[RECOVERY.md](RECOVERY.md). Nếu đang xử lý sự cố này, dùng chart đã trích xuất theo
RECOVERY. Các lệnh upgrade bên dưới dùng artifact chart này; kiểm tra nó tồn tại trước khi chạy.

Đợt ngày 2026-11-07 lưu trạng thái E1 thực tế trước E3 trong
`.generated/e3/pre-e3-20261107T083008Z/`, vì backup trước E1 không còn.
Điểm khôi phục của đợt này là E1 (min 3 worker, NodePool e1-orders), không phải
baseline trước E1. Kết quả và quá trình khôi phục được ghi tại FINAL-REPORT.md/CLEANUP.md.
Các bước lưu baseline tổng quát bên dưới dành cho đợt chạy mới.

Chạy từng khối lệnh trong Bash/Git Bash, kiểm tra kết quả rồi mới sang bước tiếp theo.
Các lệnh thay đổi cluster thực thi ngay. Hướng dẫn dùng Helm 4, context `twolevel-dev`,
region `us-east-1`, namespace `retailstore` và queue `orders-queue` như repo hiện tại.
Helm 3 không có cờ `--server-side=false`; bỏ cờ này nếu đang dùng Helm 3.

Mỗi terminal phải mở ở `experiments/E3`. Từ thư mục gốc repo, chạy:

```bash
cd experiments/E3
```

Không cần triển khai lại Terraform, KEDA, Karpenter, monitoring hay build lại image
nếu các thành phần từ E1 vẫn hoạt động. Không push lại tag `latest` giữa các lượt;
đối chiếu image digest để chắc chắn các lượt dùng cùng bản ứng dụng.

## 1. Kế hoạch đo

Giữ nguyên workload và thông số đã dùng ở E1: `BATCH_SIZE`, `WORK_UNITS`, `DB_MODE`,
`VUS`, concurrency, image và queue. Mặc định k6 của E3 là batch 1, work units 100,
DB mode light, 50 VU. Nếu E1 dùng giá trị khác, đặt lại đúng giá trị đó ở terminal
phát tải. Các biến này ảnh hưởng job thực tế; metadata do init tạo chưa ghi chúng,
summary k6 mới ghi thông số workload thực tế.

| Nhánh | Controller | Điều kiện đầu |
|---|---|---|
| hpa | CPU target 60%, min 1/max 10 | Một node E3 Ready, một worker Ready |
| keda | SQS queueLength 10, min 1/max 10 | Một node E3 Ready, một worker Ready |

Đợt chạy hiện tại chọn hai lượt hợp lệ/nhánh/profile theo [RUNS.md](RUNS.md), thứ tự
Step → Burst → Steady, tổng 12 lượt. Cặp Step r01 đã thu và được giữ với các giới
hạn đã ghi trong báo cáo. Tăng attempt nếu chạy lại, không ghi đè kết quả đã thu;
không trộn lượt có cấu hình khác vào cùng bảng so sánh. Báo cáo thể hiện n=2 và
không khẳng định khác biệt thống kê ổn định từ số lượt này.

Step kéo dài 7 phút; Burst 2 phút 30 giây. Thu ít nhất 75 giây trước tải và ít nhất
60 giây sau tải, lâu hơn nếu queue chưa drain. Cửa sổ report mặc định vẫn là 60 giây
trước/sau tải; giữ cùng cửa sổ khi so sánh. Nếu đổi `--after`, phải thu đủ thời gian
và dùng cùng giá trị cho mọi report được so sánh.

## 2. Kết thúc E1, lưu baseline E3

```bash
aws sts get-caller-identity
helm version --short
kubectl --context twolevel-dev get nodes -o wide
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects
bash ./run.sh inspect --context twolevel-dev --namespace retailstore --deployment orders-worker
```

Nếu E1 chưa khôi phục, thực hiện mục **5. Khôi phục** trong [E1 README](../E1/README.md)
trước. Lệnh của mục đó dùng đường dẫn tương đối giống nhau khi đang ở E3, nhưng
hãy kiểm tra rõ file baseline `../../.generated/e1/` tồn tại và đúng môi trường.
Không gỡ KEDA/Karpenter controller hay node hệ thống. Chỉ gỡ tài nguyên E1 sau khi
đã dừng tải, drain queue, kiểm tra owner và chuyển worker ra khỏi node E1.

Trước khi tiếp tục, kết quả inspect phải không còn controller nào trỏ đến
`orders-worker`. Nếu còn scaler chung hoặc tên khác E1/E3, xác định nguồn quản lý
của nó trước; không xóa hàng loạt HPA/ScaledObject trong namespace. Worker không
được còn chọn NodePool `e1-orders` đã gỡ.

Sau khi khôi phục E1 và kiểm tra không có controller quản lý worker, lưu baseline
E3 một lần. Chỉ tiếp tục nếu cả hai lệnh lưu thành công và hai file có nội dung:

```bash
umask 077
mkdir -p ../../.generated/e3

(set -o noclobber; helm get values orders -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e3/orders-original-values.yaml)
(set -o noclobber; kubectl --context twolevel-dev -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e3/orders-original-replicas.txt)

test -s ../../.generated/e3/orders-original-values.yaml
test -s ../../.generated/e3/orders-original-replicas.txt
```

Nếu file đã tồn tại, kiểm tra đó có phải baseline E3 đã lưu đúng từ trước hay không.
Không lấy cấu hình đang chạy E3 để ghi đè baseline và không dùng file rỗng để restore.

## 3. Tạo NodePool E3 một lần

Kiểm tra release/tên E3 chưa tồn tại. `helm status` báo release chưa tồn tại là bình
thường ở lần đầu. Nếu đã tồn tại, kiểm tra nguồn gốc và dùng phần reset ở mục 8
cho tài nguyên E3 của bạn; không chạy lại `helm install` lên release đang tồn tại.

```bash
helm status e3-capacity -n karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodepool e3-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e3-orders --ignore-not-found
kubectl --context twolevel-dev -n retailstore get hpa e3-orders-cpu --ignore-not-found
kubectl --context twolevel-dev -n retailstore get scaledobject e3-orders-sqs --ignore-not-found
```

Render và kiểm tra cấu hình; dùng AMI/runtime đã hoạt động trong E1:

```bash
helm template e3-capacity ../../kubernetes/charts/platform-config -n karpenter \
  -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml

helm install e3-capacity ../../kubernetes/charts/platform-config -n karpenter --kube-context twolevel-dev \
  -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s

kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e3-orders nodepool/e3-orders --timeout=900s
```

NodePool riêng `e3-orders` dùng On-Demand `c7i-flex.large`, consolidation `Never`.
Node không tự giảm do consolidation sau tải; mục 8 sẽ đưa node về điều kiện đầu.

## 4. Chuẩn bị điều kiện đầu cho mỗi lượt

Lần đầu thực hiện sau mục 3; các lần sau thực hiện sau reset ở mục 8.
Nếu vẫn còn node E3 từ lượt trước, reset trước khi tiếp tục.

Tạo một node bằng Pod giữ chỗ rồi xóa Pod giữ chỗ:

```bash
kubectl --context twolevel-dev -n retailstore apply -f ./warm-capacity.yaml
kubectl --context twolevel-dev -n retailstore rollout status deployment/e3-warm-capacity --timeout=900s
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e3-orders -o wide

kubectl --context twolevel-dev -n retailstore get deployment e3-warm-capacity --show-labels
kubectl --context twolevel-dev -n retailstore delete deployment e3-warm-capacity --wait=true
kubectl --context twolevel-dev -n retailstore wait --for=delete pod -l app=e3-warm-capacity --timeout=300s
```

Phải có đúng một node E3 Ready. Nếu `wait` báo không có Pod vì Pod đã xóa xong,
kiểm tra `kubectl get pods -l app=e3-warm-capacity -n retailstore --context twolevel-dev`
không còn tài nguyên là được.

Triển khai một worker lên node E3, chưa áp dụng controller:

```bash
helm upgrade orders ../../.generated/e3/orders-chart-revision21 \
  -n retailstore --kube-context twolevel-dev \
  -f ../../.generated/e3/orders-original-values.yaml -f ./autoscaled-values.yaml \
  --set worker.replicaCount=1 --server-side=false --wait --timeout 900s

kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas=1
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore get deployment orders-worker -o jsonpath='{.spec.template.spec.nodeSelector}{"\n"}'
kubectl --context twolevel-dev -n retailstore get pods -o wide
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e3-orders -o wide
kubectl --context twolevel-dev describe nodes -l karpenter.sh/nodepool=e3-orders
```

Selector worker phải trỏ `e3-orders`; không được đồng thời bị ràng buộc vào node
hệ thống hoặc NodePool khác. Kiểm tra worker Ready, requests 500m/256Mi, image
digest và capacity còn trống; API, KEDA/Karpenter và monitoring chạy ngoài node E3.
Nếu Helm conflict, xử lý baseline/controller/managed fields trước; không ép ghi đè
conflict để tiếp tục đo. Không bắt đầu khi rollout thất bại.

## 5. Chọn đúng một controller

**Nếu đo HPA**, chỉ chạy:

```bash
kubectl --context twolevel-dev -n retailstore apply -f ./hpa.yaml
kubectl --context twolevel-dev -n retailstore describe hpa e3-orders-cpu
kubectl --context twolevel-dev -n retailstore top pods
```

CPU metric phải có giá trị; điều kiện `AbleToScale` và `ScalingActive` phải True.
Nếu CPU là `<unknown>`, kiểm tra metrics-server và request CPU trước khi đo.

**Nếu đo KEDA**, chỉ chạy:

```bash
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e3-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore describe hpa e3-orders-keda-hpa
```

Nhánh KEDA có ScaledObject và HPA do KEDA tạo. Không áp dụng thêm HPA CPU riêng.

Chờ ổn định về một worker desired/Ready, queue/DLQ rỗng. Pod khởi động có thể làm
CPU tăng tạm thời; chỉ bắt đầu thu khi đủ điều kiện. Preflight ở mục 6 sẽ kiểm tra
controller, queue, node, worker và target Prometheus.

## 6. Thu dữ liệu bằng hai terminal

Giữ riêng hai terminal ở E3. Nếu port-forward từ E1 vẫn chạy, kiểm tra đúng service
và dùng lại; không khởi động thêm tiến trình chiếm cùng port.

### Terminal A — Prometheus và collector

Nếu chưa có port-forward Prometheus, chạy:

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
```

Chọn nhánh/profile/attempt đúng lượt đang chuẩn bị. Ví dụ HPA Step lần 1:

```bash
VARIANT=hpa
LOAD_PROFILE=step
ATTEMPT=1
RUN_DIR="../results/E3/E3-${VARIANT}-${LOAD_PROFILE}-r$(printf '%02d' "$ATTEMPT")"

bash ./run.sh init --variant "$VARIANT" --profile "$LOAD_PROFILE" --attempt "$ATTEMPT"
bash ./run.sh collect --run-dir "$RUN_DIR" --check
```

Nếu `--check` thành công, điền điều kiện đầu vào `$RUN_DIR/notes.md`, rồi chạy:

```bash
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Chờ dòng **ĐANG THU**, rồi đợi ít nhất **75 giây**. Giữ terminal mở.
Không dùng `--duration` cho lượt chính vì thời gian drain có thể dài hơn dự kiến.

### Terminal B — k6

Nếu chưa có port-forward Orders, chạy:

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
```

Sau baseline 75 giây ở terminal A, đặt đúng cùng RUN_DIR và chạy tải:

```bash
RUN_DIR=../results/E3/E3-hpa-step-r01
bash ./run.sh load step "$RUN_DIR"
```

Cho Burst, đổi cả profile khi init, RUN_DIR và lệnh `load burst`. Cho KEDA, đổi
variant thành `keda` và chắc chắn đã chọn controller KEDA ở mục 5. Đặt lại các biến
workload nếu E1 đã dùng giá trị khác mặc định. Không đặt biến môi trường `PROFILE`,
`LOW_RATE` hoặc `HIGH_RATE`; các script cố định lịch phát tải.

### Kết thúc lượt

Sau khi k6 kết thúc, tiếp tục thu ít nhất **60 giây**, và lâu hơn đến khi collector
hiển thị ít nhất ba mẫu liên tiếp:

```text
SQS visible=0 in-flight=0 delayed=0
```

Đối chiếu thêm DLQ/job. Nếu không drain, giữ bằng chứng và điều tra; không purge
queue để biến lượt lỗi thành lượt hợp lệ. Khi đã đủ thời gian và drain, nhấn
**Ctrl+C một lần** ở terminal A, đợi xuất Prometheus và dòng **Đã lưu**. Không đổi
replica, xóa controller hoặc reset node trong lúc collector còn thu/xuất dữ liệu.

Nếu `load` hoặc collector lỗi sau khi đã tạo output, dùng attempt mới cho lượt
chạy lại. Giữ dữ liệu lỗi và ghi nguyên nhân trong notes.

## 7. Xuất report và kiểm tra số liệu

Trong terminal đã kết thúc collector:

```bash
RUN_DIR=../results/E3/E3-hpa-step-r01
bash ./run.sh report --run-dir "$RUN_DIR"
cat "$RUN_DIR/collection-summary.md"
python -m json.tool "$RUN_DIR/report.json"
```

| Nguồn | Kiểm tra |
|---|---|
| `raw/k6-summary.json` | Accepted, failed requests, dropped iterations và thông số workload |
| `collection.json`, `collection-summary.md` | Trạng thái finished/partial, lỗi và nguồn metric thiếu |
| `report.json` | Peak queue, p95, throughput, drain, Pod-minutes, Node-minutes, CPU, Pending |
| `events/collect-before.json` | Worker/image/node/cấu hình đầu lượt |
| `events/collect-worker-samples.jsonl` | Diễn biến desired/Ready, Pod và node đặt Pod |
| `events/collect-topology-samples.jsonl` | Node/NodeClaim và FailedScheduling |
| `metrics/collect-sqs-after.json` | Queue và DLQ cuối lượt |
| `notes.md` | Điều kiện đầu, sự cố, khác biệt giữa lượt và đánh giá hợp lệ |

Đặc biệt, E1 đã ghi nhận counter success không khớp accepted và CPU thiếu ở một số
lượt. E3 cần kiểm tra các file Prometheus `worker_tasks_processed_total`,
`worker_job_e2e_latency_seconds_bucket`, `worker_cpu_counter` trong `metrics/` có
dữ liệu hữu ích trước khi chạy nhiều lượt. CPU HPA hoạt động qua metrics-server
không tự bảo đảm CPU Prometheus đã được thu. Không thay missing/null bằng 0.

`pending_pod_observed` và node thay đổi có thể là hành vi cần quan sát, không tự
động làm lượt vô hiệu. Phân biệt Pending do thiếu capacity với lỗi image, taint,
IAM, quota hoặc cấu hình. Report mặc định `validity: not_assessed`; ghi đánh giá
và lý do vào notes. Success counter/histogram không thay đối soát job ID.

Report mặc định lấy nhiều metric đến 60 giây sau tải; drain và số success đến drain
được xử lý riêng. Nếu drain muộn hơn, p95 mặc định không mô tả đầy đủ mọi job đến
drain. Ghi giới hạn này hoặc chốt cửa sổ dài hơn trước các lượt chính. Report không
ghi đè `report.json` đã tồn tại.

## 8. Reset trước lượt tiếp theo

Thực hiện sau khi tải đã dừng, queue drain, collector kết thúc và report đã xuất.
Chỉ thực hiện với tài nguyên E3 của bạn sau khi kiểm tra owner.

Nếu lượt vừa chạy HPA, kiểm tra label owner `e3`, rồi gỡ HPA:

```bash
kubectl --context twolevel-dev -n retailstore get hpa e3-orders-cpu --show-labels
kubectl --context twolevel-dev -n retailstore delete hpa e3-orders-cpu --wait=true
```

Nếu lượt vừa chạy KEDA, kiểm tra owner và gỡ ScaledObject, HPA do KEDA tạo, auth:

```bash
kubectl --context twolevel-dev -n retailstore get scaledobject e3-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e3-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e3-orders-keda-hpa --ignore-not-found
```

Nếu HPA KEDA vẫn còn, chờ nó biến mất:

```bash
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e3-orders-keda-hpa --timeout=120s
```

Sau đó kiểm tra owner của auth rồi gỡ:

```bash
kubectl --context twolevel-dev -n retailstore get triggerauthentication e3-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e3-orders-sqs-auth --wait=true
```

Xác nhận không còn controller trỏ worker, rồi tắt worker ngoài cửa sổ đo:

```bash
bash ./run.sh inspect --context twolevel-dev --namespace retailstore --deployment orders-worker
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas=0
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e3-orders -o wide
```

Kiểm tra Pod còn trên từng node E3:

```bash
for E3_NODE in $(kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e3-orders -o jsonpath='{.items[*].metadata.name}'); do
  kubectl --context twolevel-dev get pods -A --field-selector "spec.nodeName=$E3_NODE" -o wide
done
```

Chỉ tiếp tục nếu worker đã dừng, Pod giữ chỗ đã xóa và không còn ứng dụng cần giữ
trên node E3. Các DaemonSet hệ thống vẫn có thể hiện diện. Lệnh dưới chấm dứt
NodeClaim/node/EC2 thuộc E3; không áp dụng cho NodePool khác:

```bash
kubectl --context twolevel-dev delete nodeclaims -l karpenter.sh/nodepool=e3-orders --wait=true --timeout=900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e3-orders
```

Chờ không còn node/NodeClaim E3 rồi quay lại **mục 4**, tạo một node mới và một
worker, chọn nhánh, chạy với attempt mới. Giữ release NodePool E3; không chạy lại
`helm install`. Cách reset này chuẩn bị lại node trước mỗi lượt; cần ghi AZ,
capacity còn trống và image cache/digest vì node mới có thể khác điều kiện thực tế.

## 9. So sánh các lượt chính

Ví dụ dưới giả sử r01–r03 đều là lượt chính hợp lệ; nếu r01 là pilot đã loại thì
thay bằng đúng các run ID được chọn. Chỉ đưa các report cùng profile vào một lệnh:

```bash
bash ./run.sh compare \
  ../results/E3/E3-hpa-step-r01/report.json \
  ../results/E3/E3-hpa-step-r02/report.json \
  ../results/E3/E3-hpa-step-r03/report.json \
  ../results/E3/E3-keda-step-r01/report.json \
  ../results/E3/E3-keda-step-r02/report.json \
  ../results/E3/E3-keda-step-r03/report.json
```

Muốn lưu bảng, thêm `> ../results/E3/comparison-step.md` sau lệnh. Chọn tên mới nếu
file đã tồn tại. Tạo bảng Burst bằng các report Burst tương ứng. Công cụ hiển thị
trung vị [min–max]; không tự lọc lượt không hợp lệ. Chênh lệch cấu hình/workload/
cửa sổ sẽ bị từ chối; không sửa số liệu để vượt kiểm tra.

Lưu cả thư mục run gồm raw/metrics/events/logs/notes, bảng so sánh và các ảnh Grafana
đã dùng. Xác định run ID và cửa sổ UTC trên mỗi hình. Node-minutes là ước lượng
từ node Kubernetes E3, không phải số tiền EC2 trên hóa đơn.

## 10. Khôi phục sau khi hoàn tất E3

Thực hiện phần gỡ controller và scale worker về 0 của mục 8. Sau đó khôi phục:

```bash
test -s ../../.generated/e3/orders-original-values.yaml
test -s ../../.generated/e3/orders-original-replicas.txt

helm upgrade orders ../../.generated/e3/orders-chart-revision21 \
  -n retailstore --kube-context twolevel-dev \
  -f ../../.generated/e3/orders-original-values.yaml --server-side=false --wait --timeout 900s

kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e3/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
kubectl --context twolevel-dev -n retailstore get pods -o wide
helm status e3-capacity -n karpenter --kube-context twolevel-dev
```

Xác nhận worker đã rời node E3, không còn workload cần giữ trên node E3 và release
đúng của thí nghiệm, rồi gỡ capacity:

```bash
helm uninstall e3-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e3-orders
```

Kiểm tra EC2 E3 thực tế đã thu hồi. Giữ baseline và kết quả. Mỗi terminal chỉ dừng
port-forward do chính nó tạo: `kill "$PROM_PID"` ở A hoặc `kill "$ORDERS_PID"` ở B.
Nếu port-forward được dùng lại từ trước, dùng đúng terminal/PID quản lý tiến trình đó.

## Tài liệu đối chiếu

- [E3 README](README.md): cấu hình và thiết kế thí nghiệm trong repo.
- [Kubernetes HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/): metric CPU và điều khiển replica.
- [Karpenter disruption](https://karpenter.sh/docs/concepts/disruption/): consolidation và xóa NodeClaim/node.
