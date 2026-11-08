# E7 — Queue Target Sensitivity

E7 khảo sát ảnh hưởng của `queueLength` trong KEDA với ba cấu hình q-low=5, q-medium=10, q-high=20 đến số worker, backlog, latency và tài nguyên. Chỉ đổi queue target; giữ cùng workload, worker, node capacity, max replica và cửa sổ. Phạm vi báo cáo hiện tại dùng một lượt Step cho mỗi mức.

Tất cả lệnh chạy từ `experiments/E7`; workload, manifests, init, collector và report nằm ngay đây. KEDA/Karpenter/API/monitoring cần node hệ thống độc lập. Kiểm tra quota/IAM/subnet và chi phí trước khi chạy. KEDA min 1/max 10, polling 30s, cooldown 300s; NodePool `e7-orders` On-Demand, worker request 500m/256Mi. Thay đổi request so với E0 có thể ảnh hưởng throughput. Step 5→10→15→20→15→10→5/s, mỗi bậc 1 phút; Burst 5→40→5/s với đỉnh 30 giây; Steady 5/s 2 phút. Khi áp dụng manifest, KEDA cảnh báo với cấu hình hiện tại `minReplicaCount=1`, không có `idleReplicaCount` hoặc cached metrics, polling/cooldown không điều khiển scale thông thường; HPA dùng metric KEDA để scale.

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

Ví dụ pilot q-low-step-r01, dùng port-forward Prometheus `localhost:9090` và Orders `localhost:8082` đã mở. **Terminal 1:**

```bash
RUN_DIR=../results/E7/E7-q-low-step-r01
bash ./run.sh init --variant q-low --profile step --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Chờ `ĐANG THU` rồi tối thiểu 75 giây baseline. **Terminal 2:**

```bash
RUN_DIR=../results/E7/E7-q-low-step-r01
unset PROFILE LOW_RATE HIGH_RATE BATCH_SIZE WORK_UNITS VUS DB_MODE BASE_URL
bash ./run.sh load step "$RUN_DIR"
```

Sau khi workload kết thúc, chờ ít nhất 60 giây và tiếp tục đến khi queue/DLQ được đối chiếu và drain theo nhiều mẫu. Nhấn Ctrl+C một lần tại collector, đợi xuất metric. Đổi `RUN_DIR`, variant và attempt cho mỗi lượt; các file không ghi đè. Nếu port-forward chưa mở, khởi động lại theo [hướng dẫn observability](../../docs/OBSERVABILITY.md) và port-forward service `orders` đến 8082.

## 4. Báo cáo

```bash
bash ./run.sh report --run-dir "$RUN_DIR"
```

Mặc định report dùng 60 giây idle trước và 60 giây sau workload cho Node-minutes, tính từ node Kubernetes được lấy mẫu; không thay thế EC2 billing. Pod-minutes/throughput bắt đầu từ workload. SQS xấp xỉ, histogram latency có thể chứa error/duplicate và thiếu Pod sống ngắn. `collection-summary.md`, `report.json`, `events/collect-worker-samples.jsonl` và `events/collect-topology-samples.jsonl` là bằng chứng; collector không tự khẳng định lượt hợp lệ hoặc thu đủ log Pod biến mất. Ghi timestamps, node, image digest, bất thường và validity trong `notes.md`.

Dùng `compare` trên report của ba mức cùng profile, workload, worker/queue và cửa sổ; đối chiếu desired/ready replicas, backlog, drain, throughput, p95 và Pod-minutes. Nếu thay queue target so với 5/10/20 phải sửa manifest, mapping kiểm tra và ghi lại thiết kế trước khi chạy.

```bash
bash ./run.sh compare ../results/E7/E7-q-low-step-r01/report.json ../results/E7/E7-q-medium-step-r01/report.json ../results/E7/E7-q-high-step-r01/report.json
```

### 4.1. Kết quả E7 — Step v4, một lượt mỗi mức

**Mục tiêu và cơ chế:** đánh giá sự đánh đổi khi thay target backlog `queueLength` của KEDA. KEDA lấy metric SQS gồm visible và in-flight, HPA điều chỉnh số worker theo target trung bình trên mỗi replica, trong giới hạn 1–10. Với cùng queue, target nhỏ hơn có xu hướng đề xuất nhiều replica hơn; số thực tế còn phụ thuộc thời điểm lấy metric, scale-up/down và giới hạn HPA. Ví dụ đơn giản: 60 message chia cho target 5, 10, 20 tương ứng 12, 6, 3 replica trước khi áp dụng giới hạn và hành vi HPA.

**Thiết kế:** mỗi mức dùng một lượt Step v4 `5 → 10 → 15 → 20 → 15 → 10 → 5 request/s`, mỗi bậc 60 giây; tổng lý thuyết 4.800 request. Cả ba dùng batchSize=1, workUnits=100, dbMode=light, worker concurrency=1, request 500m CPU/256Mi, cùng image digest `sha256:5e02055690df084186cc06246ed3cf239ca24c62515b57b4e09382747d450a27`. Queue là `orders-queue`, region `us-east-1`; KEDA/HPA min 1/max 10. Cùng bốn node On-Demand `c7i-flex.large` được giữ xuyên suốt. Mỗi lượt bắt đầu với một worker, queue/DLQ rỗng và Prometheus target UP; thu baseline ít nhất 75 giây, workload 7 phút và tiếp tục thu sau tải đến khi queue được xác nhận drain.

**Xác nhận validity: hợp lệ cho so sánh mô tả trong phạm vi một lượt mỗi mức**, theo quyết định sử dụng một lượt của nhóm. Cả ba collector hoàn tất không có lỗi/cảnh báo tự động; k6 có 4.799 accepted, 0 request lỗi và không ghi nhận dropped iteration; CloudWatch ghi 4.799 sent và 4.799 deleted mỗi lượt. DLQ không có message trong các mẫu, worker trở về 1 Ready, không thấy Pod Pending, image và tập bốn node E7 giữ nguyên trong và giữa các lượt. Chấp nhận sai lệch 1 request so với tổng lý thuyết, vì cùng xuất hiện ở cả ba lượt và không có dropped iteration được ghi nhận; không suy diễn nguyên nhân sai lệch. Các hạn chế đo và đối soát bên dưới vẫn áp dụng; validity không chứng minh job hoàn thành đúng duy nhất hay độ lặp thống kê.

| Chỉ số | q-low = 5 | q-medium = 10 | q-high = 20 |
|---|---:|---:|---:|
| Run ID | `q-low-step-r01` | `q-medium-step-r01` | `q-high-step-r01` |
| Accepted / request lỗi | 4.799 / 0 | 4.799 / 0 | 4.799 / 0 |
| Replica desired/ready cao nhất quan sát được | 9/9 | 6/6 | 3/3 |
| Peak backlog visible + in-flight, xấp xỉ | 26 | 51 | 43 |
| p95 E2E, giây, xấp xỉ | 0,572 | 1,659 | 1,344 |
| Throughput thành công trong workload, job/s, xấp xỉ | 11,12 | 11,16 | 11,25 |
| Ready Pod-minutes, xấp xỉ | 45,7 | 33,0 | 18,5 |
| Xác nhận drain đầu tiên sau tải, giây, xấp xỉ | 99,0 | 92,3 | 117,1 |
| CPU worker trung bình cộng các Pod, core, xấp xỉ | 1,14 | 1,13 | 1,15 |
| Node-minutes Kubernetes, xấp xỉ | 36,01 | 36,00 | 36,00 |
| Chạm max=10 theo mẫu | Không | Không | Không |

**Phân tích:** trong ba lượt này, tăng target 5 → 10 → 20 đi cùng đỉnh replica 9 → 6 → 3 và Pod-minutes giảm. q-high dùng ít hơn q-low khoảng 59,5% Pod-minutes; throughput tổng gần nhau quanh 11,1–11,3 job/s. Đây là throughput toàn bộ worker trong workload, không phải năng lực một worker. μ E0 ≈ 8,9 task/s/worker là ước lượng sơ bộ khi một worker bão hòa, dùng làm mốc thiết kế tải; không thể so sánh trực tiếp hoặc giả định giữ nguyên khi E7 đổi CPU request.

q-low có p95 thấp nhất trong ba lượt (0,572 giây); q-high dùng ít Pod-minutes nhất, với p95 1,344 giây. q-medium có p95 và peak backlog cao nhất trong bộ mẫu, nhưng các kết quả không tăng đều theo target; một lượt mỗi mức không đo được độ biến động hoặc chứng minh quan hệ nhân quả chính xác. Không có nhánh nào quan sát thấy chạm trần 10. Tất cả giữ bốn node, nên Pod-minutes thấp hơn không trực tiếp làm giảm tiền EC2 trong thiết kế này; Node-minutes là thời gian node Kubernetes có mặt, không phải billing.

**Kết luận:** nếu ưu tiên latency thấp trong các lượt đã đo, q-low=5 là ứng viên; nếu ưu tiên giảm tài nguyên worker và chấp nhận p95 khoảng 1,344 giây, q-high=20 là ứng viên. Chưa chọn được mức tối ưu chung vì nhóm chưa đặt mục tiêu latency; kết quả chỉ mô tả một lượt mỗi mức.

**Cách đọc và giới hạn:** p95 được ước lượng từ histogram E2E theo thời điểm hoàn thành, có thể chứa error/duplicate và thiếu Pod sống ngắn; không phải HTTP p95. Throughput là chênh lệch counter success trong 420 giây workload chia thời gian, có thể bỏ job xử lý trước scrape đầu của Pod mới. Report success đến drain lần lượt 4.689/4.709/4.763; chênh với accepted không chứng minh mất job, cũng không thể tự kết luận mọi job thành công: SQS sent/deleted là số lượt thao tác và không đối soát job ID duy nhất. SQS backlog là xấp xỉ; drain là thời điểm ba mẫu rỗng liên tiếp đầu tiên sau tải, không phải thời gian chính xác job cuối. Pod-minutes và CPU dùng cửa sổ từ đầu tải đến 60 giây sau tải; Node-minutes dùng thêm 60 giây trước tải. Một lượt/mức không cho min–max hay độ tin cậy thống kê.

Bằng chứng: [q-low](../results/E7/E7-q-low-step-r01/notes.md), [q-medium](../results/E7/E7-q-medium-step-r01/notes.md), [q-high](../results/E7/E7-q-high-step-r01/notes.md); mỗi thư mục chứa `report.json`, `collection-summary.md`, k6 summary, mẫu worker/topology/SQS và đối chiếu CloudWatch. `collection.json` và collection summary giữ trạng thái đánh giá tại lúc thu; xác nhận sau thu nằm trong metadata, report và notes.

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
# Nếu ScaledObject E2 đã được lưu khi chuyển từ E6 sang E7:
if test -s ../../.generated/e7/e2-scaledobject-original.json; then
  kubectl --context twolevel-dev -n retailstore apply -f ../../.generated/e7/e2-scaledobject-original.json
  kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e2-orders-sqs --timeout=300s
fi
```

Xác minh worker đã rời node của thí nghiệm, node không còn workload cần giữ và Helm release đúng owner, rồi mới gỡ NodePool (có thể chấm dứt EC2):

```bash
helm status e7-capacity -n karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e7-orders -o wide
helm uninstall e7-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e7-orders
```

Giữ baseline khi chưa xác nhận phục hồi. Kiểm tra EC2 thực sự đã thu hồi; không gỡ node hệ thống hoặc controller chung.
