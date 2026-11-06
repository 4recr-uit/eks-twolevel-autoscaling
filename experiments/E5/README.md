# E5 — Cold start và Cron pod pre-warming

So sánh KEDA scale-to-zero (`cold`) với giữ sẵn một (`warm-1`) hoặc hai worker (`warm-2`) bằng Cron. Cả ba nhánh đều giữ node worker Ready và đủ capacity để tập trung vào pod, không trộn thời gian cấp node vào first-job latency.

Chạy mọi lệnh từ `experiments/E5` trong hai Git Bash; file cấu hình, workload và công cụ của thí nghiệm đều ở đây. Các chart nền trong project và chart Orders của backend vẫn là phụ thuộc triển khai. **Mới được chuẩn bị trong repo, chưa pilot trên cluster.** Giữ nguyên dữ liệu lượt trước; không đổi nhãn hay trộn vào thiết kế mới.

| Variant | Manifest KEDA | Trạng thái trước first job |
|---|---|---|
| `cold` | `keda-cold.yaml` | Worker 0 |
| `warm-1` | `keda-warm-1.yaml` | Cron đang active, 1 worker Ready |
| `warm-2` | `keda-warm-2.yaml` | Cron đang active, 2 worker Ready |

## File

- `karpenter-values.yaml`: NodePool/NodeClass `e5-orders`, On-Demand, node 2 vCPU, `consolidateAfter: Never`. E4 có thêm `karpenter-node-zero-values.yaml` để cho phép consolidation sau 1 phút.
- `autoscaled-values.yaml`, `keda*.yaml`: selector worker và ScaledObject SQS min 0/max 10, queueLength 10, polling 30 giây, cooldown 300 giây. Chỉ một controller độc lập được quản lý worker.
- `node-anchor.yaml`: Pod giữ node worker trong nhánh cần node sẵn, không phải worker. Kiểm tra resource, Pod/IP trống và placement thực tế.
- `run.py`, `run.sh`: tạo hồ sơ, kiểm tra target và lệnh tắt tại chỗ; script không tự apply/xóa cluster.
- `first_job.py`: gửi một job có ID, lưu response/timestamp; khi lỗi không tự gửi lại để tránh tạo job trùng.
- `collect.py`: chỉ đọc SQS/DLQ, Prometheus, worker, Node, NodeClaim và scheduler event; lấy log có job ID được chọn khi Pod còn tồn tại. `snapshot.py` là tùy chọn chỉ đọc.
- `report.py`, `compare.py`: thống kê first job và metric có sẵn; `stead.js`, `step.js`, `burst.js`, `workload-common.js` là workload tại chỗ nếu muốn thêm tải.

Giữ cùng image/digest, requests/limits, concurrency, database, queue, lịch idle, workload và node type giữa các nhánh. KEDA/Karpenter và hệ thống đo cần có node hệ thống riêng. Kiểm tra IAM, quota EC2, subnet, Pod/IP, giá và các tên tài nguyên; node tạo ra phát sinh phí. **Không purge queue.**

## 1. Kiểm tra và lưu baseline

Cần `kubectl`, Helm 4, AWS CLI, Python 3, k6 (nếu thêm tải) và Prometheus. Xác nhận context/region, queue và DLQ rỗng, không có producer/consumer khác, HPA/ScaledObject khác không quản lý worker. Dừng nếu các tên thí nghiệm đã thuộc tài nguyên khác.

```bash
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects
kubectl --context twolevel-dev get nodes -o wide
kubectl --context twolevel-dev get nodepool e5-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e5-orders --ignore-not-found
kubectl --context twolevel-dev -n retailstore get scaledobject e5-orders-sqs --ignore-not-found
kubectl --context twolevel-dev -n retailstore get triggerauthentication e5-orders-sqs-auth --ignore-not-found
helm status e5-capacity -n karpenter --kube-context twolevel-dev
```

`helm status` có thể báo release chưa tồn tại. Lưu baseline, không ghi đè; dừng nếu lệnh thất bại:

```bash
umask 077
mkdir -p ../../.generated/e5
test ! -e ../../.generated/e5/orders-original-values.yaml && helm get values orders -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e5/orders-original-values.yaml
test ! -e ../../.generated/e5/orders-original-replicas.txt && kubectl --context twolevel-dev -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e5/orders-original-replicas.txt
test -s ../../.generated/e5/orders-original-values.yaml && test -s ../../.generated/e5/orders-original-replicas.txt
```

## 2. Chuẩn bị node, worker và scaler

Sau khi kiểm tra tên/release chưa tồn tại, render và cài NodePool. 

```bash
helm template e5-capacity ../../kubernetes/charts/platform-config -n karpenter -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e5-capacity ../../kubernetes/charts/platform-config -n karpenter --kube-context twolevel-dev -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e5-orders nodepool/e5-orders --timeout=900s
```

Ở cả ba nhánh áp dụng `node-anchor.yaml` để giữ node worker sẵn. Mỗi lượt chỉ apply **một** manifest KEDA từ bảng trên; Cron và SQS nằm cùng ScaledObject, không dùng HPA độc lập.

```bash
# Chỉ chạy lệnh anchor ở nhánh cần giữ node:
kubectl --context twolevel-dev -n retailstore apply -f ./node-anchor.yaml
kubectl --context twolevel-dev -n retailstore rollout status deployment/e5-node-anchor --timeout=900s
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e5-orders -o wide
```

Áp dụng worker rồi manifest tương ứng:

```bash
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e5/orders-original-values.yaml -f ./autoscaled-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda-cold.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e5-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects,deployments,pods -o wide
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e5-orders -o wide
```

`--server-side=false` dành cho Helm 4; nếu conflict, dừng kiểm tra managed fields và autoscaler. Không tự dùng `--force-conflicts`. Kiểm tra kỹ trạng thái ở bảng variant, queue/DLQ, Prometheus và cấu hình thực tế trước lượt. Hai manifest Cron mẫu có timezone `Asia/Ho_Chi_Minh`, start 00:00 và end 23:59 mỗi ngày; phải điều chỉnh lịch theo thí nghiệm, xác nhận cửa sổ hiện tại active và ghi lịch/giờ trong notes. Không mặc định worker sẵn chỉ vì đã apply.

## 3. Chạy lượt bằng hai terminal

Ví dụ `cold-idle-r01`; đổi variant, profile và attempt tương ứng. `idle` chỉ gửi một first job; có thể chọn `step`, `burst` hoặc `steady` để chạy thêm workload sau first job. Mỗi lượt dùng thư mục riêng.

**Terminal 1:**

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E5/E5-cold-idle-r01
bash ./run.sh init --variant cold --profile idle --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Sau dòng `ĐANG THU`, chờ ít nhất **75 giây** trước first job để có đủ 60 giây mẫu idle. `--check` kiểm tra một phần, không thay cho đối chiếu cluster/queue và Cron.

**Terminal 2:**

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E5/E5-cold-idle-r01
bash ./run.sh first --run-dir "$RUN_DIR"
```

`first` lưu `raw/first-job.json` và ID; chỉ chạy một lần mỗi lượt. Nếu lệnh báo lỗi hoặc trạng thái `unknown`, **không gửi lại trong cùng lượt**: kiểm tra queue/job trước vì request có thể đã tới API. Collector cố gắng lưu log đúng ID ở `logs/collect-first-job.jsonl`. Chờ job hoàn thành; nếu dùng profile `step`/`burst`/`steady`, tiếp tục với `bash ./run.sh load step "$RUN_DIR"` hoặc profile tương ứng. Không chạy `load` với profile `idle`.

Sau first job và workload tùy chọn, tiếp tục thu đến khi queue drain. Trong nhánh Cron, worker có thể tiếp tục chạy trong cửa sổ pre-warm; không yêu cầu về 0 khi Cron còn active. Ghi thời lượng idle và lịch Cron thực tế. Nhấn **Ctrl+C một lần** ở collector sau khi đã quan sát đủ, chờ xuất Prometheus xong. Dừng port-forward của từng terminal bằng `kill "$PROM_PID"` và `kill "$ORDERS_PID"` tương ứng.

## 4. Báo cáo

```bash
RUN_DIR=../results/E5/E5-cold-idle-r01
bash ./run.sh report --run-dir "$RUN_DIR"
# Ví dụ so sánh: đưa đường dẫn report.json của các nhánh cùng profile
bash ./run.sh compare "$RUN_DIR/report.json" ../results/E5/E5-warm-1-idle-r01/report.json
```

`report.json` có first-job latency theo đúng job ID nếu thu được log, mốc trigger active/desired/Pod Ready, queue peak/drain, số worker, CPU, NodeClaim/node và Pod-minutes idle 60 giây. p95/p99 dựa trên histogram tối đa 120 giây đầu, có thể gồm lỗi/duplicate. Trigger active dùng thời điểm condition hoặc proxy mẫu; NodeClaim/Node Ready chỉ là mốc ứng viên, cần đối chiếu Pod và node/claim; không tự kết luận quan hệ nhân quả. Nếu Pod biến mất trước khi lấy log hoặc metric thiếu, kết quả là `N/A`, không được tự thay bằng 0. Samples, SQS và counters có sai số; kiểm tra `collection-summary.md`, `events/` và `notes.md`. Không ghi đè report; đánh giá validity và lý do thủ công. So sánh yêu cầu cùng profile, worker/queue, tham số first-job và cửa sổ idle. Chạy ít nhất 3 lượt hợp lệ mỗi nhánh nếu điều kiện cho phép.

## 5. Khôi phục

Sau khi dừng tải và drain, kiểm tra owner/names; chỉ xóa tài nguyên của lượt này. Giữ baseline nếu có lỗi:

```bash
kubectl --context twolevel-dev -n retailstore get scaledobject e5-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e5-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e5-orders-keda-hpa --ignore-not-found
# Nếu HPA còn tồn tại:
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e5-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore get triggerauthentication e5-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e5-orders-sqs-auth --wait=true
test -s ../../.generated/e5/orders-original-values.yaml && test -s ../../.generated/e5/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e5/orders-original-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e5/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
```

Kiểm tra worker đã rời node thí nghiệm và không còn workload cần giữ; kiểm tra owner trước khi xóa anchor/release. Việc gỡ NodePool có thể chấm dứt EC2:

```bash
kubectl --context twolevel-dev -n retailstore get deployment e5-node-anchor --ignore-not-found --show-labels
# Chỉ nếu anchor do lượt này tạo:
kubectl --context twolevel-dev -n retailstore delete deployment e5-node-anchor --ignore-not-found --wait=true
helm status e5-capacity -n karpenter --kube-context twolevel-dev
helm uninstall e5-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e5-orders
```

Kiểm tra cả EC2, giữ baseline cho các lượt còn lại và không gỡ KEDA/Karpenter hoặc node hệ thống.
