# E6 — Elastic On-Demand vs Spot

So sánh chi phí và hiệu năng **KEDA + Karpenter Elastic** trên EC2 On-Demand và Spot. Baseline là E1 Config 1 Elastic Step r01/r02; nhánh Spot dùng riêng NodePool `e6-spot-orders`. Mỗi lượt bắt đầu với **1 worker Ready trên đúng 1 node worker**, không có node dự phòng, sau đó Karpenter có thể mở rộng. System node vẫn chạy controller, API và monitoring.

- **Workload:** Step v4, 5→10→15→20→15→10→5 request/s, mỗi bậc 1 phút; `BATCH_SIZE=1`, `WORK_UNITS=100`, `DB_MODE=light`, `VUS=50`.
- **Worker/KEDA:** request 500m/256Mi, concurrency 1; queueLength 10, min 1/max 10, polling 30s, cooldown 300s, giống E1 Config 1. `karpenter-values.yaml` dùng Spot `c7i-flex.large`, consolidation `Never`, nhằm đối chiếu E1. Một loại instance/AZ có thể không có Spot capacity; không tự chuyển On-Demand.
- **Cửa sổ chi phí:** 525 giây từ lúc k6 bắt đầu, gồm khoảng 420 giây tải và 105 giây sau tải. Nếu queue chưa drain tại 525 giây, tiếp tục thu đến khi drain và ghi riêng; không coi toàn bộ job đã hoàn thành trong cửa sổ. Node Kubernetes được lấy mẫu là proxy EC2 runtime, không gồm thời gian trước/sau cửa sổ.
- **Giá tham khảo:** On-Demand $0,0848/giờ; Spot minimum $0,0275/giờ từ [Vantage](https://instances.vantage.sh/), cần xác nhận `us-east-1`, loại instance, OS và ngày. Spot thật dùng giá theo AZ và thời điểm chạy; giá minimum chỉ là giả định. Việc tính cost/1.000 dùng giả định job API chấp nhận đều thành công; chưa đối soát theo job ID.

Các file `karpenter-values.yaml`, `keda.yaml`, `autoscaled-values.yaml`, `step.js`, `run.sh`, `collect.py`, `report.py`, `window.py` và `cost.py` nằm trong E6. Karpenter cần quyền Spot/service-linked role, subnet/IP và quota; Terraform có cấu hình interruption queue nhưng phải xác nhận trên cluster. Ghi image digest, node type/AZ, capacity trống, giá và khác biệt so với E1. Không suy ra độ ổn định Spot từ các lượt không có interruption.

**Đã triển khai ngày 08/11/2026:** NodePool, KEDA E6 và một worker Spot đã Ready; preflight queue/DLQ và Prometheus đạt. Nếu trạng thái này vẫn còn, bắt đầu từ mục 2, không cài lại mục 1. ScaledObject E2 được sao lưu và tạm gỡ để nhường worker cho E6; file khôi phục nằm trong `.generated/e6/e2-scaledobject-original.json`. Node E2 không bị gỡ. Node Spot E6 tiếp tục phát sinh chi phí khi idle; xem mục 4 để khôi phục sau lượt.

## 1. Kiểm tra và chuẩn bị

Chạy từ `experiments/E6` trong Git Bash. Xác nhận context, region, IAM/quota, queue/DLQ rỗng và không có producer/consumer khác. Nếu HPA hoặc ScaledObject khác đang quản lý `orders-worker`, dừng và xử lý ownership trước; không xóa tài nguyên của lượt khác. Các tên E6 và release phải chưa tồn tại. Giữ E1 results và baseline gốc.

```bash
kubectl --context twolevel-dev -n retailstore get deployment orders-worker
kubectl --context twolevel-dev -n retailstore get hpa,scaledobjects
kubectl --context twolevel-dev get nodes,nodeclaims -o wide
kubectl --context twolevel-dev get nodepool e6-spot-orders --ignore-not-found
kubectl --context twolevel-dev get ec2nodeclass e6-spot-orders --ignore-not-found
kubectl --context twolevel-dev -n retailstore get scaledobject e6-spot-orders-sqs --ignore-not-found
kubectl --context twolevel-dev -n retailstore get triggerauthentication e6-spot-orders-sqs-auth --ignore-not-found
helm status e6-spot-capacity -n karpenter --kube-context twolevel-dev
```

Lưu baseline **một lần**, không ghi đè. Nếu đã lưu từ đợt E6 này, đối chiếu baseline trước khi tái sử dụng; dừng nếu không chắc nguồn hoặc file thiếu.

```bash
umask 077
mkdir -p ../../.generated/e6
test ! -e ../../.generated/e6/orders-original-values.yaml && helm get values orders -n retailstore --kube-context twolevel-dev -o yaml > ../../.generated/e6/orders-original-values.yaml
test ! -e ../../.generated/e6/orders-original-replicas.txt && kubectl --context twolevel-dev -n retailstore get deployment orders-worker -o jsonpath='{.spec.replicas}' > ../../.generated/e6/orders-original-replicas.txt
test -s ../../.generated/e6/orders-original-values.yaml && test -s ../../.generated/e6/orders-original-replicas.txt
```

Sau khi xác nhận queue đã drain và không còn controller khác, render/cài NodePool, chuyển placement của worker rồi áp dụng KEDA E6:

```bash
helm template e6-spot-capacity ../../kubernetes/charts/platform-config -n karpenter -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml
helm install e6-spot-capacity ../../kubernetes/charts/platform-config -n karpenter --kube-context twolevel-dev -f ../../kubernetes/environments/dev/platform.yaml -f ./karpenter-values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/e6-spot-orders nodepool/e6-spot-orders --timeout=900s
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e6/orders-original-values.yaml -f ./autoscaled-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore apply -f ./keda.yaml
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e6-spot-orders-sqs --timeout=300s
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e6-spot-orders -o wide
```

Chờ đúng một worker Ready và một node Spot Ready; so sánh image digest và spare capacity với E1. Nếu Helm conflict, rollout lỗi hoặc Spot không cấp phát được, dừng kiểm tra; không tự force-conflicts hay đổi loại capacity. `collect --check` xác nhận controller/queue, node Spot và worker; không tự xác nhận quota, interruption handling hay capacity trống tương đương.

## 2. Thu một lượt

Mỗi terminal ở `experiments/E6`. **Terminal 1:**

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090 &
PROM_PID=$!
RUN_DIR=../results/E6/E6-elastic-step-r01
bash ./run.sh init --variant elastic --profile step --attempt 1
bash ./run.sh collect --run-dir "$RUN_DIR" --check
bash ./run.sh collect --run-dir "$RUN_DIR"
```

Chờ `ĐANG THU`, sau đó đợi ít nhất 75 giây baseline. **Terminal 2:**

```bash
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80 &
ORDERS_PID=$!
RUN_DIR=../results/E6/E6-elastic-step-r01
bash ./run.sh load step "$RUN_DIR"
```

Sau khi k6 dừng, chờ **ít nhất 120 giây**, lâu hơn nếu queue chưa drain; kiểm tra nhiều mẫu visible/in-flight/delayed, DLQ, lỗi và job. Nhấn Ctrl+C một lần tại collector và đợi xuất xong; dừng port-forward ở từng terminal bằng `kill "$PROM_PID"` hoặc `kill "$ORDERS_PID"`. Mốc 120 giây cho phép thu qua cuối cửa sổ 525 giây; report sẽ từ chối nếu workload hoặc collection không phủ đủ cửa sổ. Ghi validity, AZ và interruption trong `notes.md`.

```bash
bash ./run.sh report --run-dir "$RUN_DIR"
```

Với lượt tiếp theo, khôi phục và chuẩn bị lại đúng một node/worker ban đầu; đổi attempt và RUN_DIR, không ghi đè kết quả. Không tự xóa node đang có workload để tạo điều kiện đầu.

## 3. Tính chi phí

`window.py` tạo input cho `cost.py` từ E1 Elastic Step hoặc E6 Spot, tích phân node theo từng type/AZ trong đúng 525 giây. Tham số giá là **một giá cho mọi AZ và toàn bộ cửa sổ**: kiểm tra và sửa từng nhóm trong input nếu giá Spot thực tế khác nhau/thay đổi. Giá sau chỉ là ví dụ theo ảnh, không phải giá Spot được xác nhận cho lượt mới.

```bash
bash ./run.sh window --run-dir ../results/E1/E1-elastic-step-r01 --hourly-price 0.0848 --price-date 2026-11-08 --price-source 'Vantage On-Demand reference' --assume-accepted-success --output ../results/E1/E1-elastic-step-r01/e6-cost-input.json
bash ./run.sh window --run-dir "$RUN_DIR" --hourly-price 0.0275 --price-date 2026-11-08 --price-source 'Vantage Spot minimum example; replace with actual AZ/time price' --assume-accepted-success --output "$RUN_DIR/e6-cost-input.json"
bash ./run.sh cost ../results/E1/E1-elastic-step-r01/e6-cost-input.json "$RUN_DIR/e6-cost-input.json" --baseline E1-elastic-step-r01-525s
```

Chỉ chạy lệnh Spot sau khi xác minh và thay giá/ngày/nguồn phù hợp; `--assume-accepted-success` thể hiện giả định, không xác nhận hoàn thành. Input/output không ghi đè. `cost.py` không tính EKS, node hệ thống, NAT, RDS, storage/network hay EC2 billing adjustments. Đọc `report.json` và raw để đối chiếu drain, latency, errors, job và capacity trước khi kết luận.

## 4. Khôi phục sau lượt

Sau drain, kiểm tra owner tài nguyên E6 và baseline trước khi gỡ scaler. Sau đó khôi phục worker về baseline; chỉ gỡ release E6 khi worker đã rời node E6 và node không chứa workload cần giữ. Gỡ release có thể chấm dứt EC2.

```bash
kubectl --context twolevel-dev -n retailstore get scaledobject e6-spot-orders-sqs --show-labels
kubectl --context twolevel-dev -n retailstore delete scaledobject e6-spot-orders-sqs --wait=true
kubectl --context twolevel-dev -n retailstore get hpa e6-spot-orders-keda-hpa --ignore-not-found
# Nếu HPA còn: kubectl --context twolevel-dev -n retailstore wait --for=delete hpa/e6-spot-orders-keda-hpa --timeout=120s
kubectl --context twolevel-dev -n retailstore get triggerauthentication e6-spot-orders-sqs-auth --show-labels
kubectl --context twolevel-dev -n retailstore delete triggerauthentication e6-spot-orders-sqs-auth --wait=true
test -s ../../.generated/e6/orders-original-values.yaml && test -s ../../.generated/e6/orders-original-replicas.txt
helm upgrade orders ../../../retailstore-backend-microservices/src/orders/chart -n retailstore --kube-context twolevel-dev -f ../../.generated/e6/orders-original-values.yaml --server-side=false --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas="$(cat ../../.generated/e6/orders-original-replicas.txt)"
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=900s
# Nếu đã lưu ScaledObject E2 khi chuyển sang E6, khôi phục lại:
if test -s ../../.generated/e6/e2-scaledobject-original.json; then
  kubectl --context twolevel-dev -n retailstore apply -f ../../.generated/e6/e2-scaledobject-original.json
  kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready scaledobject/e2-orders-sqs --timeout=300s
fi
kubectl --context twolevel-dev get nodes,nodeclaims -l karpenter.sh/nodepool=e6-spot-orders -o wide
helm status e6-spot-capacity -n karpenter --kube-context twolevel-dev
helm uninstall e6-spot-capacity -n karpenter --kube-context twolevel-dev --wait --timeout 900s
```

Kiểm tra node/NodeClaim và EC2 thực sự đã thu hồi; giữ baseline nếu khôi phục chưa xong. Không gỡ KEDA/Karpenter controller hay node hệ thống.

## 5. Kết quả Step sơ bộ

**Thiết kế:** Biến so sánh là loại capacity của node worker: On-Demand (E1 Config 1 Elastic) và Spot (E6 Elastic). Mỗi nhánh có hai lượt Step v4, bắt đầu với một worker/node, queue và DLQ rỗng. Các lượt dùng cùng image digest, request 500m/256Mi, concurrency 1 và `c7i-flex.large`; cấu hình KEDA theo manifest E1/E6 là min 1/max 10, queueLength 10. Chỉ thay capacity type theo thiết kế, nhưng khác biệt thực tế về AZ, thời gian cấp phát và biến động workload không được kiểm soát hoàn toàn. Các snapshot E1 cũ không lưu đầy đủ spec ScaledObject tại đầu lượt.

**Phương pháp:** So sánh đúng 525 giây từ đầu workload; tính tổng node-seconds theo từng instance/AZ, nhân đơn giá giờ rồi chia cho 3.600. Cost/1.000 job dùng giả định toàn bộ job được API chấp nhận đều hoàn thành; chưa đối soát job ID. Node Kubernetes là proxy EC2 runtime, không phải billing. Giá On-Demand tham khảo $0,0848/giờ; giá Spot theo AWS Spot Price History trong hai lượt: `us-east-1a` $0,0308/giờ, `us-east-1b` $0,0309/giờ. Giá và chi phí chỉ áp dụng cho worker EC2 trong cửa sổ, không gồm EKS, node hệ thống, NAT, RDS, EBS, network hoặc thời gian ngoài cửa sổ.

| Lượt | Node-phút ≈ | Chi phí ≈ USD | p95 E2E ≈ s | Peak queue ≈ |
|---|---:|---:|---:|---:|
| E1 On-Demand r01 | 8,75 | 0,01237 | 0,249 | 24 |
| E1 On-Demand r02 | 15,40 | 0,02176 | 1,114 | 47 |
| E6 Spot r01 | 15,29 | 0,00786 | 1,354 | 43 |
| E6 Spot r02 | 8,75 | 0,00449 | 0,902 | 41 |

### Trung bình mỗi cấu hình

| Chỉ số | On-Demand | Spot |
|---|---:|---:|
| Node-phút ≈ | 12,07 | 12,02 |
| Chi phí worker EC2 / lượt ≈ USD | 0,01706 | 0,00618 |
| Chi phí / 1.000 job giả định hoàn thành ≈ USD | 0,00356 | 0,00129 |
| p95 E2E trung bình của từng lượt ≈ giây | 0,682 | 1,128 |
| Peak queue trung bình ≈ message | 35,5 | 42,0 |
| Xác nhận drain sau khi dừng tải trung bình ≈ giây | 82,7 | 98,3 |

Các số là trung bình số học, không phải percentile tính gộp tất cả job. Trung bình chi phí worker EC2 của Spot thấp hơn khoảng **63,8%** trong các lượt và cửa sổ đã đo; node-phút trung bình gần nhau, phù hợp với việc đơn giá Spot thấp hơn. Latency và backlog trung bình của Spot cao hơn trong mẫu nhỏ này, nhưng chưa đủ dữ liệu để kết luận có khác biệt ổn định hoặc do Spot gây ra.

**Giới hạn:** Hai lượt mỗi nhánh là kết quả thăm dò; report vẫn `validity: not_assessed`, histogram/counter và SQS là ước lượng. Lượt Spot r02 xác nhận drain khoảng 0,35 giây sau cuối cửa sổ; có mẫu queue bằng 0 trước cuối cửa sổ nhưng chưa xác nhận drain trong cửa sổ. Chưa có phép thử interruption có chủ đích hoặc đủ bằng chứng để kết luận độ ổn định/khả năng phục hồi Spot. Thêm lượt hợp lệ, đối soát job ID và đo thời gian EC2 thực nếu cần kết luận mạnh hơn. Xem [đầu vào và tổng hợp chi phí](../results/E6/cost-step-525s/comparison.json); thư mục kết quả không được theo dõi trong Git.
