# E4 — KEDA worker scale-to-zero

So sánh/quan sát `pod-zero` (worker về 0, node worker giữ sẵn) và phần mở rộng `node-zero` (cả node worker về 0). API, KEDA, Karpenter, monitoring và các dịch vụ hệ thống vẫn chạy trên node hệ thống; không coi toàn bộ cluster hay chi phí AWS về 0.

Chạy mọi lệnh từ `experiments/E4` trong hai Git Bash; file cấu hình, workload và công cụ của thí nghiệm đều ở đây. Các chart nền trong project và chart Orders của backend vẫn là phụ thuộc triển khai. **Mới được chuẩn bị trong repo, chưa pilot trên cluster.** Giữ nguyên dữ liệu lượt trước; không đổi nhãn hay trộn vào thiết kế mới.

| Variant | NodePool | Anchor | Trạng thái trước first job |
|---|---|---|---|
| `pod-zero` | `karpenter-values.yaml` (consolidation Never) | Có `node-anchor.yaml` | Worker 0, node worker Ready và đủ capacity |
| `node-zero` | `karpenter-node-zero-values.yaml` (consolidation 1m) | Không | Worker 0, node worker/NodeClaim về 0; kiểm tra EC2 thực tế |

## File

- `karpenter-values.yaml`: NodePool/NodeClass `e4-orders`, On-Demand, node 2 vCPU, `consolidateAfter: Never`. E4 có thêm `karpenter-node-zero-values.yaml` để cho phép consolidation sau 1 phút.
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
kubectl --context twolevel-dev get nodepool e4-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e4-orders --ignore-not-found
kubectl --context twolevel-dev -n retailstore get scaledobject e4-orders-sqs --ignore-not-found
kubectl --context twolevel-dev -n retailstore get triggerauthentication e4-orders-sqs-auth --ignore-not-found
helm status e4-capacity -n karpenter --kube-context twolevel-dev
```

`helm status` có thể báo release chưa tồn tại. Lưu baseline, không ghi đè; dừng nếu lệnh thất bại:

```bash
umask 077
mkdir -p ../../.generated/e4
test ! -e ../../.generated/e4/orders-original-values.yaml && helm get values orders -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e4/orders-original-values.yaml
test ! -e ../../.generated/e4/orders-original-replicas.txt && kubectl --context twolevel-dev -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e4/orders-original-replicas.txt
test -s ../../.generated/e4/orders-original-values.yaml && test -s ../../.generated/e4/orders-original-replicas.txt
```

## 2. Chuẩn bị node, worker và scaler

Sau khi kiểm tra tên/release chưa tồn tại, render và cài NodePool. Với node-zero thay cả hai lần `karpenter-values.yaml` bằng `karpenter-node-zero-values.yaml`.

```bash
helm template e4-capacity ../../kubernetes/charts/platform-config -n karpenter -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e4-capacity ../../kubernetes/charts/platform-config -n karpenter --kube-context twolevel-dev -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e4-orders nodepool/e4-orders --timeout=900s
```

Với `pod-zero`, áp dụng anchor để giữ node. Với `node-zero`, **không** áp dụng anchor, dùng overlay `karpenter-node-zero-values.yaml` ở bước tạo NodePool và chờ mọi node/NodeClaim worker được thu hồi trước khi gửi job.

```bash
# Chỉ chạy lệnh anchor ở nhánh cần giữ node:
kubectl --context twolevel-dev -n retailstore apply -f ./node-anchor.yaml
kubectl --context twolevel-dev -n retailstore rollout status deployment/e4-node-anchor --timeout=900s
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e4-orders -o wide
```

Áp dụng worker rồi manifest tương ứng:

```bash
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e4/orders-original-values.yaml -f ./autoscaled-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e4-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects,deployments,pods -o wide
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e4-orders -o wide
```

`--server-side=false` dành cho Helm 4; nếu conflict, dừng kiểm tra managed fields và autoscaler. Không tự dùng `--force-conflicts`. Kiểm tra kỹ trạng thái ở bảng variant, queue/DLQ, Prometheus và cấu hình thực tế trước lượt. Với node-zero, xác nhận node và NodeClaim worker đã mất và EC2 tương ứng đã thu hồi, trong khi system node/controller vẫn hoạt động.

## 3. Chạy lượt bằng hai terminal

Ví dụ `pod-zero-idle-r01`; đổi variant, profile và attempt tương ứng. `idle` chỉ gửi một first job; có thể chọn `step`, `burst` hoặc `steady` để chạy thêm workload sau first job. Mỗi lượt dùng thư mục riêng.

**Terminal 1:**

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E4/E4-pod-zero-idle-r01
bash ./run.sh init --variant pod-zero --profile idle --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Sau dòng `ĐANG THU`, chờ ít nhất **75 giây** trước first job để có đủ 60 giây mẫu idle. `--check` kiểm tra một phần, không thay cho đối chiếu cluster/queue và Cron.

**Terminal 2:**

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E4/E4-pod-zero-idle-r01
bash ./run.sh first --run-dir "$RUN_DIR"
```

`first` lưu `raw/first-job.json` và ID; chỉ chạy một lần mỗi lượt. Nếu lệnh báo lỗi hoặc trạng thái `unknown`, **không gửi lại trong cùng lượt**: kiểm tra queue/job trước vì request có thể đã tới API. Collector cố gắng lưu log đúng ID ở `logs/collect-first-job.jsonl`. Chờ job hoàn thành; nếu dùng profile `step`/`burst`/`steady`, tiếp tục với `bash ./run.sh load step "$RUN_DIR"` hoặc profile tương ứng. Không chạy `load` với profile `idle`.

Sau first job và khi tải dừng, tiếp tục thu đến khi queue drain và worker về 0. Cooldown KEDA mẫu là 300 giây; thực tế có thể lâu hơn. Với `node-zero`, tiếp tục quan sát node và EC2 được thu hồi; không xóa controller hoặc system node. Nhấn **Ctrl+C một lần** ở collector sau khi đã quan sát đủ, chờ xuất Prometheus xong. Dừng port-forward của từng terminal bằng `kill "$PROM_PID"` và `kill "$ORDERS_PID"` tương ứng.

## 4. Báo cáo

```bash
RUN_DIR=../results/E4/E4-pod-zero-idle-r01
bash ./run.sh report --run-dir "$RUN_DIR"
# Ví dụ so sánh: đưa đường dẫn report.json của các nhánh cùng profile
bash ./run.sh compare "$RUN_DIR/report.json" ../results/E4/E4-node-zero-idle-r01/report.json
```

`report.json` có first-job latency theo đúng job ID nếu thu được log, mốc trigger active/desired/Pod Ready, queue peak/drain, số worker, CPU, NodeClaim/node và Pod-minutes idle 60 giây. Dùng `worker_zero_observed_after_drain_seconds` để đánh giá worker về 0 sau lượt; mốc zero sau first-job có thể xảy ra trước workload tùy chọn. p95/p99 dựa trên histogram tối đa 120 giây đầu, có thể gồm lỗi/duplicate. Trigger active dùng thời điểm condition hoặc proxy mẫu; NodeClaim/Node Ready chỉ là mốc ứng viên, cần đối chiếu Pod và node/claim; không tự kết luận quan hệ nhân quả. Nếu Pod biến mất trước khi lấy log hoặc metric thiếu, kết quả là `N/A`, không được tự thay bằng 0. Samples, SQS và counters có sai số; kiểm tra `collection-summary.md`, `events/` và `notes.md`. Không ghi đè report; đánh giá validity và lý do thủ công. So sánh yêu cầu cùng profile, worker/queue, tham số first-job và cửa sổ idle. Chạy ít nhất 3 lượt hợp lệ mỗi nhánh nếu điều kiện cho phép.

## 5. Khôi phục

Sau khi dừng tải và drain, kiểm tra owner/names; chỉ xóa tài nguyên của lượt này. Giữ baseline nếu có lỗi:

```bash
kubectl --context twolevel-dev -n retailstore get scaledobject e4-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e4-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e4-orders-keda-hpa --ignore-not-found
# Nếu HPA còn tồn tại:
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e4-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore get triggerauthentication e4-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e4-orders-sqs-auth --wait=true
test -s ../../.generated/e4/orders-original-values.yaml && test -s ../../.generated/e4/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e4/orders-original-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e4/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
```

Kiểm tra worker đã rời node thí nghiệm và không còn workload cần giữ; kiểm tra owner trước khi xóa anchor/release. Việc gỡ NodePool có thể chấm dứt EC2:

```bash
kubectl --context twolevel-dev -n retailstore get deployment e4-node-anchor --ignore-not-found --show-labels
# Chỉ nếu anchor do lượt này tạo:
kubectl --context twolevel-dev -n retailstore delete deployment e4-node-anchor --ignore-not-found --wait=true
helm status e4-capacity -n karpenter --kube-context twolevel-dev
helm uninstall e4-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e4-orders
```

Kiểm tra cả EC2, giữ baseline cho các lượt còn lại và không gỡ KEDA/Karpenter hoặc node hệ thống.
