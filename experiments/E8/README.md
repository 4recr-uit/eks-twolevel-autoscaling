# E8 — Worker disruption và recovery

E8 quan sát sự phục hồi khi một worker Pod bị gián đoạn lúc đang có backlog. Chạy một nhánh baseline và một nhánh fault cùng workload/cấu hình; chỉ thực hiện lỗi khi đã kiểm tra chính xác Pod, queue và điều kiện khôi phục. Không khẳng định lossless nếu chưa đối chiếu job ID/end state. Công cụ ở đây không tự xóa Pod hoặc Node.

Tất cả lệnh chạy từ `experiments/E8`; workload, manifests, init, collector và report nằm ngay đây. KEDA/Karpenter/API/monitoring phải có node hệ thống độc lập. Giá trị là pilot, **chưa xác minh trên cluster**. Kiểm tra quota/IAM/subnet và chi phí trước khi chạy. KEDA min 1/max 10, polling 30s, cooldown 300s; NodePool `e8-orders` On-Demand, worker request 500m/256Mi. Thay đổi request so với E0 có thể ảnh hưởng throughput, phải pilot lại. Step 5→10→15→20→15→10→5/s, mỗi bậc 1 phút; Burst 5→40→5/s với đỉnh 30 giây; Steady 5/s 2 phút.

## 1. Điều kiện và baseline

Kiểm tra context, node, các HPA/ScaledObject trỏ `orders-worker`, queue/DLQ, producer khác, requests/limits, region và monitoring. Dừng nếu controller khác đang quản lý worker hoặc các tên `e8-orders*`/release `e8-capacity` đã thuộc tài nguyên khác. Không purge queue. Lưu baseline không ghi đè:

```bash
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects
kubectl --context twolevel-dev get nodes,nodeclaims -o wide
kubectl --context twolevel-dev get nodepool e8-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e8-orders --ignore-not-found
helm status e8-capacity -n karpenter --kube-context twolevel-dev
umask 077
mkdir -p ../../.generated/e8
test ! -e ../../.generated/e8/orders-original-values.yaml && helm get values orders -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e8/orders-original-values.yaml
test ! -e ../../.generated/e8/orders-original-replicas.txt && kubectl --context twolevel-dev -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e8/orders-original-replicas.txt
test -s ../../.generated/e8/orders-original-values.yaml && test -s ../../.generated/e8/orders-original-replicas.txt
```

Nếu release chưa tồn tại `helm status` có thể báo lỗi. Dừng nếu baseline không lưu được. Xác nhận KEDA và Karpenter hoạt động, target Prometheus UP, quyền AWS và queue mà worker/KEDA dùng đúng.

## 2. Áp dụng cấu hình

Chỉ sau khi kiểm tra tài nguyên và release chưa tồn tại:

```bash
helm template e8-capacity ../../kubernetes/charts/platform-config -n karpenter -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e8-capacity ../../kubernetes/charts/platform-config -n karpenter --kube-context twolevel-dev -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e8-orders nodepool/e8-orders --timeout=900s
```

Không apply Pod giữ chỗ trong nhánh elastic; sau khi bật worker cần một worker Ready và kiểm tra capacity thực tế. Tài nguyên warm-capacity được cung cấp nếu cần pilot khác, nhưng phải giữ cùng điều kiện giữa baseline và fault.

```bash
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e8/orders-original-values.yaml -f ./autoscaled-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e8-orders-sqs --timeout=300s
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects,deployments,pods -o wide
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e8-orders -o wide
```

Dùng `keda.yaml` queueLength 10, min 1/max 10. E8 không bắt buộc giữ sẵn node dự phòng: ghi điều kiện đầu, capacity, NodeClaim và Pending để phân biệt thời gian khôi phục do Pod và do node. Không tự gây lỗi khi đang chạy baseline. `--server-side=false` yêu cầu Helm 4; dừng nếu rollout/conflict thất bại, không tự dùng `--force-conflicts`. Chờ đúng một desired/Ready worker và queue rỗng trước mỗi lượt.

## 3. Thu một lượt

Ví dụ baseline-burst-r01. **Terminal 1:**

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E8/E8-baseline-burst-r01
bash ./run.sh init --variant baseline --profile burst --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Chờ `ĐANG THU` rồi tối thiểu 75 giây baseline. **Terminal 2:**

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E8/E8-baseline-burst-r01
bash ./run.sh load burst "$RUN_DIR" > "$RUN_DIR/logs/k6-console.log" 2>&1 &
LOAD_PID=$!
```

Khi có backlog và chọn được worker Pod cụ thể (không chọn Pod hệ thống), ghi mốc ngay trước thao tác thủ công. Kiểm tra tên/UID và chỉ xóa Pod đã chọn; thao tác làm gián đoạn workload:

```bash
kubectl --context twolevel-dev -n retailstore get pods -l app.kubernetes.io/instance=orders,app.kubernetes.io/component=worker -o wide
POD=<ten-pod-worker-da-kiem-tra>
POD_UID=$(kubectl --context twolevel-dev -n retailstore get pod "$POD" -o jsonpath='{.metadata.uid}')
python ./mark.py --run-dir "$RUN_DIR" --pod "$POD" --pod-uid "$POD_UID"
kubectl --context twolevel-dev -n retailstore delete pod "$POD" --wait=false
wait "$LOAD_PID"
```

Dòng `POD=...` cần thay bằng Pod thực tế; chỉ chạy marker một lần cho fault. Marker là thời điểm **trước** lệnh delete, không phải timestamp chính xác của sự kiện. Baseline không gọi `mark.py` và không xóa Pod. Không tự terminate node; nếu khảo sát node riêng phải định nghĩa phương pháp, scope và bằng chứng tách biệt.

Sau khi workload kết thúc, chờ ít nhất 60 giây và tiếp tục đến khi queue/DLQ được đối chiếu và drain theo nhiều mẫu. Nhấn Ctrl+C một lần tại collector, đợi xuất metric; đóng từng port-forward bằng PID của terminal đó. Đổi `RUN_DIR`, variant và attempt cho mỗi lượt; các file không ghi đè.

## 4. Báo cáo

```bash
bash ./run.sh report --run-dir "$RUN_DIR"
```

Mặc định report dùng 60 giây idle trước và 60 giây sau workload cho Node-minutes, tính từ node Kubernetes được lấy mẫu; không thay thế EC2 billing. Pod-minutes/throughput bắt đầu từ workload. SQS xấp xỉ, histogram latency có thể chứa error/duplicate và thiếu Pod sống ngắn. `collection-summary.md`, `report.json`, `events/collect-worker-samples.jsonl` và `events/collect-topology-samples.jsonl` là bằng chứng; collector không tự khẳng định lượt hợp lệ hoặc thu đủ log Pod biến mất. Ghi timestamps, node, image digest, bất thường và validity trong `notes.md`.

Sau `report`, với lượt fault chạy `python ./recovery.py --run-dir "$RUN_DIR"`. Output cho biết khoảng từ marker đến lần đầu quan sát Pod cũ biến mất và một Pod mới Ready; đây là giới hạn theo chu kỳ lấy mẫu. Pod mới cũng có thể do scale-out, nên cần đối chiếu UID, scheduler events và desired replicas trước khi kết luận. Kiểm tra peak backlog, throughput và duplicate trong report/raw logs; thiếu job ID/end state không chứng minh lossless.

## 5. Khôi phục

Sau drain, kiểm tra ownership tài nguyên `e8-orders-sqs`, `e8-orders-sqs-auth`, HPA và baseline trước khi xóa; chỉ xóa resource thuộc lượt này:

```bash
kubectl --context twolevel-dev -n retailstore get scaledobject e8-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e8-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e8-orders-keda-hpa --ignore-not-found
# Nếu HPA còn tồn tại:
kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e8-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore get triggerauthentication e8-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e8-orders-sqs-auth --wait=true
test -s ../../.generated/e8/orders-original-values.yaml && test -s ../../.generated/e8/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e8/orders-original-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e8/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
```

Xác minh worker đã rời node của thí nghiệm, node không còn workload cần giữ và Helm release đúng owner, rồi mới gỡ NodePool (có thể chấm dứt EC2):

```bash
helm status e8-capacity -n karpenter --kube-context twolevel-dev
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e8-orders -o wide
helm uninstall e8-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e8-orders
```

Giữ baseline khi chưa xác nhận phục hồi. Kiểm tra EC2 thực sự đã thu hồi; không gỡ node hệ thống hoặc controller chung.
